"""Practice in one line (not for test day):  python scripts/practice_run.py [pack.txt] [msg1.txt ...]

Archives the current session, then runs `python main.py <file>` for the pack and each message in turn,
exactly as you would by hand. With no arguments it uses the sample pack and both practice messages.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = sys.argv[1:] or ["samples/sample_pack.txt", "samples/practice_change_printing.txt",
                         "samples/practice_wrong_caterer.txt"]
subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_session.py")], cwd=ROOT)
for f in files:
    print("\n" + "#" * 78 + f"\n# python main.py {f}\n" + "#" * 78)
    code = subprocess.run([sys.executable, str(ROOT / "main.py"), f], cwd=ROOT).returncode
    print(f"# exit code {code}")
