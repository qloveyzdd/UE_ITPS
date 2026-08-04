from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class SourceRevision:
    git_root: Path
    commit: str


def _git(cwd: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(detail or "Git command failed")
    return completed.stdout.strip()


def resolve_source_revision(
    project_file: Path,
    requested_commit: str | None = None,
) -> SourceRevision:
    project_file = project_file.resolve()
    if not project_file.is_file():
        raise ValueError(f"Project descriptor does not exist: {project_file}")
    try:
        git_root = Path(
            _git(project_file.parent, "rev-parse", "--show-toplevel")
        ).resolve()
    except ValueError as exc:
        raise ValueError(
            "Information-pool builds require the UE project to be inside Git"
        ) from exc
    head = _git(git_root, "rev-parse", "HEAD^{commit}")
    if requested_commit is not None:
        selected = _git(
            git_root,
            "rev-parse",
            f"{requested_commit}^{{commit}}",
        )
        if selected != head:
            raise ValueError(
                "The requested source commit is not the checked-out HEAD; "
                "the information pool never labels working-tree facts as "
                "another revision"
            )
    dirty = _git(
        git_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if dirty:
        raise ValueError(
            "The UE project Git worktree must be clean before building an "
            "information-pool snapshot"
        )
    return SourceRevision(git_root=git_root, commit=head)


def confirm_source_revision(revision: SourceRevision) -> None:
    current = _git(revision.git_root, "rev-parse", "HEAD^{commit}")
    dirty = _git(
        revision.git_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if current != revision.commit or dirty:
        raise ValueError(
            "The UE project changed while the candidate snapshot was being built"
        )


def require_ignored_pool(pool_directory: Path, revision: SourceRevision) -> None:
    pool_directory = pool_directory.resolve()
    try:
        relative = pool_directory.relative_to(revision.git_root)
    except ValueError:
        return
    result = subprocess.run(
        [
            "git",
            "-C",
            str(revision.git_root),
            "check-ignore",
            "--quiet",
            "--",
            (relative / ".ue-itps-ignore-probe").as_posix(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            "An information-pool directory inside the UE repository must be "
            "ignored by Git"
        )
