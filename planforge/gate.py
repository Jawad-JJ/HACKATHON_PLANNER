"""The gate every message passes through - initial pack and later updates alike.

For each message (in date order):
  1. irrelevant message            -> recorded, ignored
  2. fact outside the sender's lane -> rejected (e.g. a caterer changing our order size)
  3. quote / request / "may"        -> recorded as information, does not change the plan
  4. older than what we already have -> outdated, kept for the record only
  5. everything else is tried: re-plan with it, and if that creates a NEW hard failure
     (budget, venue, food, judging, schedule) the fact is rejected with that failure as the reason.
     The previous valid plan is kept.
"""
from . import ledger
from .planner import build_plan
from .validate import fail_set

OPTION_KINDS = {"venue_option", "food_option"}


def plan_for(facts):
    return build_plan(ledger.active_facts(facts) + [f for f in facts if f.get("info_only")])


def admit(facts: list, msg: dict, new_facts: list) -> list:
    """Mutates fact states in-place, appends accepted facts to `facts`. Returns decision lines."""
    decisions = []
    say = lambda f, verdict, why: decisions.append(  # noqa: E731
        {"message": msg["id"], "fact": f["id"], "kind": f["kind"], "verdict": verdict, "reason": why,
         "quote": f.get("quote", "")})
    if not msg["relevant"]:
        decisions.append({"message": msg["id"], "fact": None, "kind": None, "verdict": "irrelevant",
                          "reason": "no planning facts in this message", "quote": ""})
        return decisions

    candidates = []
    for f in new_facts:
        f["key"] = list(ledger.canonical(f, facts))
        problem = ledger.lane_problem(msg["role"], f["kind"])
        if problem:
            f["state"], f["reason"] = "rejected", problem
            facts.append(f)
            say(f, "rejected", problem)
            continue
        if f["kind"] == "optional_cost":
            f["approved"] = msg["role"] in ("organizer", "finance") and f["status"] == "confirmed"
        elif f["status"] in ledger.INFO_STATUSES and f["kind"] not in OPTION_KINDS:
            f["state"], f["info_only"] = "info", True
            f["reason"] = f"{f['status']} only - recorded, plan unchanged"
            facts.append(f)
            say(f, "info", f["reason"])
            continue
        same = [g for g in facts if g.get("state") in ("active", "superseded") and tuple(g["key"]) == tuple(f["key"])
                and f["kind"] not in ("judge_change", "other")]
        newest = max(same, key=lambda g: (g.get("date_iso") or "", g["order"]), default=None)
        if newest is not None and ledger.newer(newest, f):
            f["state"] = "superseded"
            f["reason"] = f"out of date: {newest['id']} ({newest.get('date_raw') or 'later'}) is newer"
            facts.append(f)
            say(f, "outdated", f["reason"])
            continue
        candidates.append(f)

    if not candidates:
        return decisions

    before = fail_set(plan_for(facts))

    def new_failures(cands):
        trial = [dict(g) for g in facts] + [dict(c, state="active") for c in cands]
        ledger.mark_superseded(trial)
        plan = plan_for(trial)
        return [i["text"] for i in plan["issues"] if i["level"] == "fail"
                and (i["area"], __import__("re").sub(r"\d[\d,]*", "#", i["text"])) not in before]

    if not new_failures(candidates):
        accepted = candidates
    else:
        accepted = []
        for c in candidates:
            errs = new_failures(accepted + [c])
            if errs:
                c["state"], c["reason"] = "rejected", "conflicts with the plan: " + "; ".join(errs)
                facts.append(c)
                say(c, "rejected", c["reason"])
            else:
                accepted.append(c)
    for c in accepted:
        c["state"] = "active"
        facts.append(c)
        say(c, "accepted", "applied")
    ledger.mark_superseded(facts)
    for c in accepted:  # report what each accepted fact replaced
        for g in facts:
            if g is not c and g.get("state") == "superseded" and g["reason"].startswith(f"replaced by newer {c['id']}"):
                for d in decisions:
                    if d["fact"] == c["id"]:
                        d["reason"] = f"applied; replaces {g['id']} ({_show(g)})"
    return decisions


def _show(f):
    for k in ("amount", "price_per_head", "count", "minutes", "value", "quantity"):
        if f.get(k) is not None:
            return f"{k} {f[k]:,}" if isinstance(f[k], int) else f"{k} {f[k]}"
    return f.get("name") or f.get("item") or f["kind"]
