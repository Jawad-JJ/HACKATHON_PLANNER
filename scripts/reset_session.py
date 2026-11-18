"""Practice helper (NOT needed on test day): archive the current session so the next run starts clean.

    python scripts/reset_session.py

On test day this is unnecessary: running a new pack starts a fresh session automatically and the
previous one is archived in state/archive/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from planforge.session import STATE_DIR, archive  # noqa: E402

if (STATE_DIR / "session.json").exists():
    archive()
    print("Session archived to state/archive/. Next run starts a new plan.")
else:
    print("No active session.")
