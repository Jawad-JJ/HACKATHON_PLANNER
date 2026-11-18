"""One pipeline for everything: python main.py <file>  (CLI)  and  POST /api/message  (web UI).

  read file -> decide new pack / update -> PREDICT and save -> one `reading` call (+1 repair max)
  -> gate each message in date order -> re-plan in code -> validate -> save -> export
"""
import json
import time

from . import ledger
from .gate import admit, plan_for
from .ingest import RawInput
from .llm import CallBudgetExceeded, LLMClient
from .reader import SYSTEM_PROMPT, build_user_prompt, parse_reading
from .session import STATE_DIR, archive, atomic_write, load, new_session, save
from .trace import to_dict
from .validate import checks, is_valid

FULL_RUN_SECONDS = 110      # brief: full run cut off at 120 s
UPDATE_SECONDS = 55         # brief: update cut off at 60 s
UPDATE_MAX_CALLS = 5        # brief: at most 5 model calls per update; we plan for 1 (2 with a repair)
PACK_MIN_BLOCKS = 4


PREDICTION = {"tags": ["reading"], "calls": 1,
              "why": "language is read once by the model; venue, schedule, food, judging and budget "
                     "are recomputed in plain code, so no area makes a model call"}


def looks_like_pack(raw: RawInput, sess) -> bool:
    """Only used to pick the time budget before the call; the final decision uses what the model read."""
    return sess is None or raw.sha256 in sess.get("pack_hashes", []) or len(raw.blocks) >= PACK_MIN_BLOCKS


def run(raw: RawInput, client: LLMClient, state_dir=STATE_DIR) -> dict:
    t0 = time.monotonic()
    old = load(state_dir)
    guess_pack = looks_like_pack(raw, old)
    run_rec = {"run_id": None, "input": raw.path, "sha256": raw.sha256, "mode": None,
               "prediction": PREDICTION, "predicted_at": time.strftime("%H:%M:%S"), "decisions": [],
               "actual_tags": [], "calls": [], "seconds": None, "status": "running"}
    atomic_write(state_dir / "prediction.json", json.dumps(run_rec, indent=1))   # on disk BEFORE any model call

    client.run_id = -1                          # provisional; renumbered when stored in the session
    client.max_calls = UPDATE_MAX_CALLS
    client.deadline = t0 + (FULL_RUN_SECONDS if guess_pack else UPDATE_SECONDS)

    # ------------------------------------------------------------------ the reading call(s)
    user = build_user_prompt(raw.blocks)
    messages, error, recs = None, "", []
    attempts = [(SYSTEM_PROMPT, user, True)]
    while attempts:
        system, prompt, jm = attempts.pop(0)
        try:
            rec = client.chat("reading", system, prompt, json_mode=jm)
        except CallBudgetExceeded as e:
            error = str(e)
            break
        recs.append(rec)
        if rec.status != "ok":
            error = rec.error
            time_left = client.deadline - time.monotonic()
            if len(recs) < 2 and time_left > 15:   # one retry, without JSON mode if that was the problem
                no_json = "response_format" in rec.error or "json" in rec.error.lower()
                attempts.append((SYSTEM_PROMPT, user, jm and not no_json))
            continue
        try:
            messages = parse_reading(rec.response, len(raw.blocks))
            break
        except Exception as e:  # noqa: BLE001
            error = f"model output was not usable JSON: {e}"
            if len(recs) < 2:
                attempts.append((SYSTEM_PROMPT, user + "\n\nReturn ONLY the JSON object described.", jm))

    # ------------------------------------------------------------------ new pack or update? (from what was read)
    n_relevant = len([m for m in (messages or []) if m["relevant"]])
    is_pack = old is None or raw.sha256 in old.get("pack_hashes", []) or n_relevant >= 3 or \
        (messages is None and guess_pack and len(raw.blocks) >= 8)
    if is_pack and old is not None and messages is not None:
        archive(state_dir)
    sess = new_session() if (is_pack and (messages is not None or old is None)) else old
    run_rec["run_id"] = len(sess["runs"]) + 1
    run_rec["mode"] = "new pack" if is_pack else "update"
    sess["runs"].append(run_rec)
    for rec in recs:
        rec.run_id = run_rec["run_id"]
        _store_call(sess, run_rec, rec)
    run_id = run_rec["run_id"]

    if messages is None:
        run_rec.update(status="failed", error=error, seconds=round(time.monotonic() - t0, 2))
        save(sess, state_dir)
        return {"session": sess, "run": run_rec, "ok": False, "error": error}

    # ------------------------------------------------------------------ gate every message in date order
    year = time.localtime().tm_year
    base_order = len(sess["messages"])
    staged = []
    for i, m in enumerate(messages):
        mid = f"M{base_order + i + 1}"
        d = ledger.parse_date(m.get("date"), year)
        if not m["blocks"]:   # model forgot block numbers: locate the block containing a quoted phrase
            for f in m["facts"]:
                q = (f.get("quote") or "").lower()
                hit = [i for i, b in enumerate(raw.blocks, 1) if q and q in b.lower()]
                if hit:
                    m["blocks"] = hit[:1]
                    break
        text = "\n".join(raw.blocks[b - 1] for b in m["blocks"]) if m["blocks"] else ""
        msg = {"id": mid, "run_id": run_id, "sender": m["sender"], "role": m["role"], "date_raw": m.get("date"),
               "date_iso": d.isoformat() if d else None, "order": base_order + i + 1, "text": text,
               "blocks": m["blocks"], "relevant": m["relevant"], "status": "", "reasons": []}
        facts = []
        for j, f in enumerate(m["facts"], 1):
            f.update(id=f"{mid}.{j}", msg=mid, order=msg["order"], date_iso=msg["date_iso"], date_raw=msg["date_raw"],
                     run_id=run_id)
            facts.append(f)
        staged.append((msg, facts))
    staged.sort(key=lambda mf: (mf[0]["date_iso"] or "9999-99-99" if is_pack else "", mf[0]["order"]))

    for msg, facts in staged:
        dec = admit(sess["facts"], msg, facts)
        verdicts = {d["verdict"] for d in dec}
        msg["status"] = ("irrelevant" if verdicts == {"irrelevant"} else
                         "rejected" if verdicts == {"rejected"} else
                         "outdated" if verdicts <= {"outdated"} else
                         "partly rejected" if "rejected" in verdicts else
                         "information only" if verdicts <= {"info", "outdated"} else "accepted")
        msg["reasons"] = [d["reason"] for d in dec if d["verdict"] in ("rejected", "outdated", "info")]
        sess["messages"].append(msg)
        run_rec["decisions"] += dec
    sess["messages"].sort(key=lambda m: m["order"])
    for m in sess["messages"]:          # messages whose every fact was replaced later are out of date
        mf = [f for f in sess["facts"] if f["msg"] == m["id"]]
        if mf and all(f["state"] == "superseded" for f in mf) and m["status"] == "accepted":
            m["status"], m["reasons"] = "outdated", [f["reason"] for f in mf]
    unassigned = sorted(set(range(1, len(raw.blocks) + 1)) - {b for m, _ in staged for b in m["blocks"]})
    run_rec["unassigned_blocks"] = [{"block": b, "text": raw.blocks[b - 1]} for b in unassigned]

    # ------------------------------------------------------------------ plan, validate, keep last valid
    plan = plan_for(sess["facts"])
    plan["checks"] = checks(plan)
    plan["valid"] = is_valid(plan)
    plan["version"] = run_id
    sess["plan"] = plan
    if plan["valid"]:
        sess["valid_plan"] = plan
    if is_pack:
        sess["pack_hashes"].append(raw.sha256)
    run_rec["actual_tags"] = sorted({c["tag"] for c in sess["calls"] if c["run_id"] == run_id})
    run_rec["prediction_matched"] = run_rec["actual_tags"] == sorted(PREDICTION["tags"])
    run_rec["plan_valid"] = plan["valid"]
    run_rec["status"] = "ok"
    run_rec["seconds"] = round(time.monotonic() - t0, 2)
    save(sess, state_dir)
    return {"session": sess, "run": run_rec, "ok": True, "error": ""}


def _store_call(sess, run_rec, rec):
    rec.number = len(sess["calls"]) + 1      # numbered within the session, in order
    d = to_dict(rec)
    sess["calls"].append(d)
    run_rec["calls"].append(rec.number)
