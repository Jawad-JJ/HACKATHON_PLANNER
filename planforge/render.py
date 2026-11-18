"""Human-readable terminal output and the files saved for submission."""
import json

from .session import OUT_DIR, atomic_write
from .trace import token_totals

W = 78


def rs(v):
    return "-" if v is None else f"Rs {v:,}"


def plan_text(plan: dict, title="EVENT PLAN") -> str:
    if not plan:
        return "No plan yet.\n"
    L = ["=" * W, f"{title}  (version {plan.get('version')})  ->  {'VALID' if plan.get('valid') else 'NOT VALID'}", "=" * W]
    p, v, f, j, s, b = (plan[k] for k in ("people", "venue", "food", "judging", "schedule", "budget"))
    L.append(f"People on site: {p['on_site']}  = {p['students']} students + {p['staff'] or 0} staff + "
             + (f"{p['volunteers']} volunteers + " if p.get("volunteers") else "") + f"{p['judges']} judges"
             + (f" + {p['other']} other" if p.get("other") else ""))
    L += ["", "[VENUE]"]
    if v["chosen"]:
        c = v["chosen"]
        L.append(f"  {c['name']}: seats {c['capacity']} for {v['people_on_site']} people, {rs(c['cost'])}  (from {c['src']})")
    for a in v["alternatives"]:
        L.append(f"    - {a['name']}: {a.get('why_not') or 'fits, but costs more'}")
    L += ["", "[SCHEDULE]  " + (f"start {s['start']}, " if s.get("start") else "relative to event start, ")
          + f"{s.get('total_minutes')} min"]
    for sl in s.get("slots", []):
        L.append(f"  {sl.get('clock') or f'+{sl['start']:>3}-{sl['end']:>3} min'}  {sl['name']}"
                 + (f"  (from {sl['src']})" if sl.get("src") else ""))
    L += ["", "[FOOD]"]
    if f["chosen"]:
        L.append(f"  {f['quantity']} x {f['chosen']['name']} @ {rs(f['chosen']['price_per_head'])} = {rs(f['cost'])}"
                 f"  (price from {f['chosen']['src']})")
        L.append(f"  Rule: {f['rule']}")
    for a in f["alternatives"]:
        L.append(f"    - {a['name']}: " + (a.get("why_not") or f"{rs(a.get('price_per_head'))}/head, would cost {rs(a.get('would_cost'))}"))
    L += ["", "[JUDGING]"]
    if j.get("judges_used"):
        L.append(f"  {j['teams']} teams, {j['judges_used']} of {j['judges_available']} judges used, "
                 f"{j['rounds']} rounds x {j['minutes_per_team']} min = {j['judging_minutes']} min, "
                 f"max {j['max_load']} teams per judge (limit {j['max_teams_per_judge']})")
        jl = [x for x in b["lines"] if str(x.get("item", "")).startswith("Judges:")]
        if jl:
            L.append(f"  Judges cost: {jl[0]['item'].split(': ', 1)[1]} = {rs(jl[0]['amount'])}")
        by_judge = {}
        for a in j["assignment"]:
            by_judge.setdefault(a["judge"], []).append(f"T{a['team']}")
        L.append("  " + "  ".join(f"J{k}:{','.join(t)}" for k, t in sorted(by_judge.items())))
    L += ["", "[BUDGET]"]
    for line in b["lines"]:
        L.append(f"  {rs(line['amount']):>14}  {line['item']}  ({line.get('src')})")
    L.append(f"  {rs(b['total']):>14}  TOTAL   cap {rs(b['cap'])}   remaining {rs(b['remaining'])}")
    if b.get("total") is not None and b.get("cap") is not None:
        L.append(f"  Budget: {rs(b['total'])} of {rs(b['cap'])} -> "
                 + ("FITS" if b["total"] <= b["cap"] else f"OVER by {rs(b['total'] - b['cap'])}"))
    for o in b["not_included"]:
        L.append(f"  not included: {o['item']} {rs(o.get('amount'))} - not approved; {o['note']} ({o['src']})")
    if plan.get("requirements"):
        L += ["", "[RULES FROM MESSAGES]"]
        L += [f"  {r['state']:<10} {r['rule']}" + (f" (actual {r['actual']})" if r.get("actual") is not None else "")
              for r in plan["requirements"]]
    if plan.get("risks"):
        L += ["", "[RISKS]"] + [f"  {r['text']} ({r['src']})" for r in plan["risks"]]
    L += ["", "[CHECKS]"] + [f"  {'PASS' if c['pass'] else 'FAIL'}  {c['check']}: {c['detail']}" for c in plan["checks"]]
    issues = [i for i in plan["issues"] if i["level"] != "fail"]
    if issues:
        L += [f"  note ({i['level']}, {i['area']}): {i['text']}" for i in issues]
    return "\n".join(L) + "\n"


def call_text(c: dict) -> str:
    L = ["-" * W, f"CALL #{c['number']}  area: {c['tag']}  model: {c['model']}  status: {c['status']}  "
                  f"({c['seconds']} s, run {c['run_id']})"]
    tok = lambda v: "unreported" if v is None else f"{v:,}"  # noqa: E731
    L.append(f"tokens as reported by the model: input {tok(c['input_tokens'])}, output {tok(c['output_tokens'])}, "
             f"total {tok(c['total_tokens'])}")
    L.append("--- input ---")
    for m in c["request"]:
        L.append(f"[{m['role']}]\n{m['content']}")
    L.append("--- output ---")
    L.append(c["response"] if c["status"] == "ok" else f"ERROR: {c['error']}")
    return "\n".join(L)


def decisions_text(decisions, sess) -> str:
    msgs = {m["id"]: m for m in sess["messages"]}
    L = []
    for d in decisions:
        m = msgs.get(d["message"], {})
        who = f"{d['message']} {m.get('sender', '')} ({m.get('date_raw') or 'no date'})"
        if d["verdict"] == "irrelevant":
            L.append(f"  IGNORED   {who}: {d['reason']}")
        else:
            L.append(f"  {d['verdict'].upper():<9} {who} {d['kind']}: {d['reason']}"
                     + (f'  ["{d["quote"]}"]' if d.get("quote") else ""))
    return "\n".join(L)


def trace_text(sess: dict, run_ids=None) -> str:
    calls = [c for c in sess["calls"] if run_ids is None or c["run_id"] in run_ids]
    runs = [r for r in sess["runs"] if run_ids is None or r["run_id"] in run_ids]
    L = ["=" * W, "MODEL CALL TRACE" + ("" if run_ids is None else f" (run {', '.join(map(str, run_ids))})"), "=" * W]
    for r in runs:
        L.append(f"Run {r['run_id']} [{r['mode']}] input {r['input']}")
        L.append(f"  prediction (saved {r['predicted_at']}, before any call): model calls in areas "
                 f"{r['prediction']['tags']} - {r['prediction']['why']}")
        for c in [c for c in calls if c["run_id"] == r["run_id"]]:
            L.append(call_text(c))
        L.append("-" * W)
        L.append(f"  actual areas that made calls: {r.get('actual_tags')}  -> prediction "
                 f"{'MATCHED' if r.get('prediction_matched') else 'did not match'}")
        if r.get("decisions"):
            L.append("  decisions (why each message was used, ignored or rejected):")
            L.append(decisions_text(r["decisions"], sess))
        if r.get("error"):
            L.append(f"  RUN FAILED: {r['error']} - previous plan kept")
    t = token_totals(calls)
    allt = token_totals(sess["calls"])
    L.append("=" * W)
    L.append(f"TOTAL TOKENS{' this run' if run_ids else ''}: input {t['input']:,} + output {t['output']:,} = "
             f"{t['total']:,} over {t['calls']} call(s)" + (f", {t['unreported_calls']} unreported" if t['unreported_calls'] else ""))
    if run_ids:
        L.append(f"TOTAL TOKENS whole session: input {allt['input']:,} + output {allt['output']:,} = {allt['total']:,} "
                 f"over {allt['calls']} call(s)")
    L.append("(sums of the counts each provider reported; nothing estimated)")
    return "\n".join(L) + "\n"


PURPOSE = {"reading": "reading the messages", "venue": "venue", "schedule": "schedule", "food": "food",
           "judging": "judging", "budget": "budget"}


def trace_summary(sess: dict, run_ids=None) -> str:
    """One line per AI call plus a total: call number, model, what it was for, tokens."""
    calls = [c for c in sess["calls"] if run_ids is None or c["run_id"] in run_ids]
    tok = lambda v: "unreported" if v is None else f"{v:,}"  # noqa: E731
    L = ["TRACE (one line per AI call)"]
    for c in calls:
        L.append(f"Call #{c['number']} | model: {c['model']} | for: {PURPOSE.get(c['tag'], c['tag'])} | "
                 f"tokens: {tok(c['input_tokens'])} in + {tok(c['output_tokens'])} out = {tok(c['total_tokens'])}"
                 + ("" if c["status"] == "ok" else f" | {c['status']}"))
    t = token_totals(calls)
    L.append(f"TOTAL: {t['calls']} call(s), {t['input']:,} in + {t['output']:,} out = {t['total']:,} tokens"
             + (f" ({t['unreported_calls']} call(s) did not report tokens)" if t["unreported_calls"] else ""))
    return "\n".join(L) + "\n"


def rejected_text(sess, run_ids=None) -> str:
    rows = [m for m in sess["messages"] if m["status"] != "accepted" and (run_ids is None or m["run_id"] in run_ids)]
    if not rows:
        return ""
    L = ["=" * W, "REJECTED / OUTDATED / IGNORED MESSAGES" + ("" if run_ids is None else " (this run)"), "=" * W]
    for m in rows:
        L.append(f"[{m['status'].upper()}] {m['id']} {m['sender']} ({m.get('date_raw') or 'no date'})")
        L.append("  \"" + (m["text"] or "").replace("\n", " ") + "\"")
        for r in (m["reasons"] or ["no planning facts in this message"]):
            L.append(f"  -> {r}")
    return "\n".join(L) + "\n"


def rejected(sess):
    return [{"message": m["id"], "sender": m["sender"], "date": m["date_raw"], "status": m["status"],
             "text": m["text"], "reasons": m["reasons"]}
            for m in sess["messages"] if m["status"] in ("rejected", "partly rejected", "outdated", "information only", "irrelevant")]


def submission_text(sess: dict) -> str:
    """Plan + rejected messages + full trace with totals: the file to upload on the form."""
    rej = "\n".join(f"- {r['message']} {r['sender']} ({r['date']}): {r['status']}\n  \"{r['text']}\"\n  "
                    + "\n  ".join(r["reasons"]) for r in rejected(sess))
    return plan_text(sess.get("plan")) + "\n" + trace_summary(sess) \
        + "\nREJECTED / OUTDATED / IGNORED MESSAGES\n" + (rej or "none") \
        + "\n\nFULL CALL DETAILS (inputs and outputs)\n" + trace_text(sess)


def export(sess: dict, out_dir=OUT_DIR) -> list:
    plan = sess.get("plan")
    files = {
        "latest_plan.json": json.dumps(plan, indent=1, ensure_ascii=False),
        "latest_plan.txt": plan_text(plan),
        "full_trace.json": json.dumps({"runs": sess["runs"], "calls": sess["calls"],
                                       "totals": token_totals(sess["calls"])}, indent=1, ensure_ascii=False),
        "full_trace.txt": trace_text(sess),
        "trace.txt": trace_summary(sess),
        "rejections.json": json.dumps(rejected(sess), indent=1, ensure_ascii=False),
        "updates.json": json.dumps([{k: r.get(k) for k in ("run_id", "mode", "input", "prediction", "actual_tags",
                                                         "prediction_matched", "plan_valid", "seconds", "status")}
                                    for r in sess["runs"]], indent=1),
        "session.json": json.dumps(sess, indent=1, ensure_ascii=False, default=str),
    }
    files["submission.txt"] = submission_text(sess)
    for name, text in files.items():
        atomic_write(out_dir / name, text)
    return [str(out_dir / n) for n in files]
