from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
from types import ModuleType
from typing import Any

RESULT_MARKER = "__UE_ITPS_EDITOR_RESULT__="
REMOTE_RECEIVE_CHUNK_SIZE = 8192
MAX_REMOTE_RESPONSE_BYTES = 64 * 1024 * 1024
REMOTE_EXECUTION_LOCK_KEY = "127.0.0.1:6776"


class EditorConnectionError(RuntimeError):
    pass


def _receive_complete_message(
    connection: Any, expected_type: str, message_type: type[Any]
) -> Any:
    data = bytearray()
    while True:
        part = connection._command_channel_socket.recv(REMOTE_RECEIVE_CHUNK_SIZE)
        if not part:
            raise RuntimeError("Remote party closed before sending a valid response")
        data.extend(part)
        if len(data) > MAX_REMOTE_RESPONSE_BYTES:
            raise RuntimeError("Remote response exceeded the 64 MiB safety limit")
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        message = message_type(None, None)
        if (
            message.from_json_bytes(bytes(data))
            and message.passes_receive_filter(connection._node_id)
            and message.type_ == expected_type
        ):
            return message
        raise RuntimeError("Remote party failed to send a valid response")


def _patch_remote_receive(remote_module: ModuleType) -> None:
    connection_type = remote_module._RemoteExecutionCommandConnection
    message_type = remote_module._RemoteExecutionMessage

    def receive_message(connection: Any, expected_type: str) -> Any:
        return _receive_complete_message(connection, expected_type, message_type)

    connection_type._receive_message = receive_message


class _ProcessLock:
    def __init__(self, key: str, timeout: float) -> None:
        digest = hashlib.sha256(key.casefold().encode("utf-8")).hexdigest()[:20]
        self.path = Path(tempfile.gettempdir()) / f"ue_itps_editor_remote_{digest}.lock"
        self.timeout = timeout
        self.handle: Any = None

    def acquire(self) -> None:
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        deadline = time.monotonic() + max(0.1, self.timeout)
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    self.release()
                    raise EditorConnectionError(
                        "Another UE editor tool is using the Remote Execution connection; retry after it completes"
                    )
                time.sleep(0.1)

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None


def _remote_execution_module() -> ModuleType:
    path = Path(__file__).resolve().parent / "vendor" / "remote_execution.py"
    if not path.is_file():
        raise EditorConnectionError(f"Bundled remote_execution.py was not found: {path}")
    module_name = f"ue_itps_remote_execution_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise EditorConnectionError(
            f"Cannot load Unreal remote execution module: {path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _patch_remote_receive(module)
    return module


def discover_sessions(
    engine_root: Path, timeout: float = 3.0
) -> list[dict[str, Any]]:
    remote_module = _remote_execution_module()
    remote = remote_module.RemoteExecution()
    remote.start()
    try:
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            nodes = list(remote.remote_nodes)
            if nodes:
                break
            time.sleep(0.1)
        else:
            nodes = []
        return sorted(
            ({str(key): value for key, value in node.items()} for node in nodes),
            key=lambda item: str(item.get("node_id", "")),
        )
    finally:
        remote.stop()


def select_session(
    sessions: list[dict[str, Any]], node_id: str
) -> dict[str, Any]:
    if not node_id:
        raise EditorConnectionError("Editor node id must not be empty")
    matches = [item for item in sessions if str(item.get("node_id")) == node_id]
    if not matches:
        raise EditorConnectionError(
            f"No running Unreal Editor session has node id {node_id}. "
            "Enable Python Remote Execution in Project Settings > Plugins > Python."
        )
    if len(matches) > 1:
        raise EditorConnectionError(
            f"Multiple Unreal Editor sessions reported the same node id: {node_id}"
        )
    return matches[0]


class EditorSession(AbstractContextManager["EditorSession"]):
    def __init__(
        self,
        node_id: str,
        *,
        discovery_timeout: float = 3.0,
    ) -> None:
        self.node_id = node_id
        self.discovery_timeout = discovery_timeout
        self._remote: Any = None
        self.node: dict[str, Any] | None = None
        self._process_lock = _ProcessLock(
            REMOTE_EXECUTION_LOCK_KEY, max(5.0, discovery_timeout)
        )

    def __enter__(self) -> "EditorSession":
        self._process_lock.acquire()
        try:
            remote_module = _remote_execution_module()
            self._remote = remote_module.RemoteExecution()
            self._remote.start()
            deadline = time.monotonic() + max(0.1, self.discovery_timeout)
            sessions: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                sessions = list(self._remote.remote_nodes)
                if any(
                    str(item.get("node_id")) == self.node_id for item in sessions
                ):
                    break
                time.sleep(0.1)
            self.node = select_session(sessions, self.node_id)
            self._remote.open_command_connection(str(self.node["node_id"]))
            return self
        except Exception:
            if self._remote is not None:
                self._remote.stop()
                self._remote = None
            self._process_lock.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._remote is not None:
            self._remote.stop()
            self._remote = None
        self._process_lock.release()

    def invoke(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        if self._remote is None:
            raise EditorConnectionError("Editor session is not connected")
        edittools_root = Path(__file__).resolve().parents[1]
        arguments_json = json.dumps(
            arguments or {}, ensure_ascii=False, separators=(",", ":")
        )
        command = "\n".join(
            [
                "import json, sys",
                f"_edittools_root = {str(edittools_root)!r}",
                "if _edittools_root not in sys.path: sys.path.insert(0, _edittools_root)",
                "for _ue_itps_module in list(sys.modules):",
                "    if _ue_itps_module.startswith('ue_editor_tools.runtime') or _ue_itps_module in {'ue_editor_tools.message_model', 'ue_editor_tools.data_asset_values', 'ue_editor_tools.blueprint_reachability'}:",
                "        sys.modules.pop(_ue_itps_module, None)",
                "from ue_editor_tools.runtime.dispatch import invoke as _ue_itps_invoke",
                f"_ue_itps_args = json.loads({arguments_json!r})",
                f"_ue_itps_value = _ue_itps_invoke({operation!r}, _ue_itps_args)",
                f"print({RESULT_MARKER!r} + json.dumps(_ue_itps_value, ensure_ascii=False, separators=(',', ':')))",
            ]
        )
        response = self._remote.run_command(command, raise_on_failure=False)
        if not response.get("success"):
            raise EditorConnectionError(
                str(response.get("result") or "Remote Editor command failed")
            )
        for item in reversed(response.get("output", [])):
            output = str(item.get("output", "")).strip()
            if output.startswith(RESULT_MARKER):
                try:
                    return json.loads(output[len(RESULT_MARKER) :])
                except json.JSONDecodeError as exc:
                    raise EditorConnectionError(
                        "Editor returned malformed JSON"
                    ) from exc
        raise EditorConnectionError(
            "Editor command completed without a structured result"
        )


def editor_identity(node: dict[str, Any]) -> dict[str, Any]:
    project_root = str(node.get("project_root", "")).replace("\\", "/").rstrip("/")
    project_name = str(node.get("project_name", ""))
    engine_root = str(node.get("engine_root", "")).replace("\\", "/").rstrip("/")
    if engine_root.casefold().endswith("/engine"):
        engine_root = engine_root[: -len("/Engine")]
    project = (
        f"{project_root}/{project_name}.uproject"
        if project_root and project_name
        else ""
    )
    return {
        "project": project,
        "project_root": project_root,
        "project_name": project_name,
        "engine_root": engine_root,
        "engine_version": str(node.get("engine_version", "")),
        "node_id": str(node.get("node_id", "")),
        "user": str(node.get("user", "")),
        "machine": str(node.get("machine", "")),
    }
