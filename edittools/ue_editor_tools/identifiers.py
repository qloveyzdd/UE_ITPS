from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_fact_id(kind: str, *parts: Any) -> str:
    """Return a deterministic identifier for an Editor fact.

    Editor Python object paths are the most stable identity exposed by the
    wrapper.  The caller should include the asset/graph path and the local
    name when creating a fact identifier.
    """

    payload = json.dumps(
        [kind, *parts], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return f"{kind}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"
