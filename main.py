"""PlanForge AI - the one command for the whole pack AND every new message:

    python main.py <messages.txt>

First run (or a file with many messages) starts a new plan; a file with one new message updates it.
"""
import sys
import time

from planforge.config import fallback_config, model_config
from planforge.ingest import read_input
from planforge.llm import LLMClient
from planforge.pipeline import PREDICTION, run
from planforge.render import export, plan_text, rejected_text, trace_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 64
    cfg = model_config()
    if cfg.problem():
        print(f"Model not configured: {cfg.problem()}. Copy .env.example to .env and fill it in.")
        return 78
    raw = read_input(argv[1])
    print(f"PREDICTION (saved before any model call): areas making model calls = {PREDICTION['tags']} "
          f"({PREDICTION['calls']} call). Venue, schedule, food, judging, budget: none.\n")
    t0 = time.monotonic()
    result = run(raw, LLMClient(cfg, fallback=fallback_config()))
    sess, r = result["session"], result["run"]
    plan = sess.get("plan")
    if plan:
        print(plan_text(plan))
    print(rejected_text(sess, [r["run_id"]]))
    print(trace_text(sess, [r["run_id"]]))
    files = export(sess)
    print(f"Saved: {', '.join(f.split('/')[-1].split(chr(92))[-1] for f in files)} in outputs/")
    print(f"Run {r['run_id']} ({r['mode']}) finished in {time.monotonic() - t0:.1f} s with "
          f"{len(r['calls'])} model call(s); plan {'VALID' if plan and plan.get('valid') else 'NOT VALID'}.")
    if not result["ok"]:
        print(f"ERROR: {result['error']}")
        return 3
    return 0 if plan and plan.get("valid") else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
