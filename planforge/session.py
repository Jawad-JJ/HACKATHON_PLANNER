"""Session state on disk (state/session.json), written atomically so a crash never corrupts it."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .config import ROOT

STATE_DIR = ROOT / "state"
OUT_DIR = ROOT / "outputs"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def new_session() -> dict:
    return {"session_id": time.strftime("%Y%m%d-%H%M%S"), "runs": [], "messages": [], "facts": [],
            "calls": [], "plan": None, "valid_plan": None, "pack_hashes": []}


def load(state_dir: Path = STATE_DIR):
    p = state_dir / "session.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(sess: dict, state_dir: Path = STATE_DIR) -> None:
    atomic_write(state_dir / "session.json", json.dumps(sess, indent=1, ensure_ascii=False, default=str))


def archive(state_dir: Path = STATE_DIR) -> None:
    p = state_dir / "session.json"
    if p.exists():
        dest = state_dir / "archive"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), dest / f"session-{time.strftime('%Y%m%d-%H%M%S')}.json")
