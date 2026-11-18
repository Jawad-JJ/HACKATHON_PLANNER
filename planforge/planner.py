"""Five planners in plain code: venue, schedule, food, judging, budget.

No model calls here. Input: active facts from the ledger. Output: a plan dict where every figure
says which fact it came from, plus a list of issues (missing data / hard failures / warnings).
"""
import math

from .reader import norm_name


def _src(f):
    return f.get("id") if f else None


class Ctx:
    """Everything the planners need, pulled from the active facts."""

    def __init__(self, facts):
        facts = [f for f in facts if not f.get("info_only")]
        self.facts = facts
        by = lambda k: [f for f in facts if f["kind"] == k]  # noqa: E731
        self.head = {norm_name(f.get("role")): f for f in by("headcount") if f.get("count") is not None}
        one = lambda k: (by(k) or [None])[0]  # noqa: E731
        self.team_size, self.teams_f, self.duration_f = one("team_size"), one("teams"), one("duration")
        self.start_f, self.cap_f, self.terms = one("start_time"), one("budget_cap"), one("judge_terms") or {}
        self.venues = [f for f in by("venue_option") if f.get("capacity") and f.get("available") is not False
                       and (f.get("cost") is not None or f.get("cost_per_hour") is not None)]
        self.unavailable = [f for f in by("venue_option") + by("food_option") if f.get("available") is False]
        self.foods = sorted([f for f in by("food_option") if f.get("price_per_head") is not None
                             and f.get("available") is not False],
                            key=lambda f: f.get("first_order", f["order"]))
        self.committed = by("committed_cost")
        self.optional = by("optional_cost")
        self.judge_changes = by("judge_change")
        self.items = by("schedule_item")
        self.reqs = by("requirement")
        self.features = by("feature_requirement")
        self.others = by("other")
        self.orders = by("order_change")


def _count(ctx, role):
    f = ctx.head.get(role)
    return (int(f["count"]), f) if f else (None, None)


def _metric_ok(value, op, target):
    if value is None or target is None:
        return None
    return {">=": value >= target, "<=": value <= target, "==": value == target}.get(op, None)


def _reqs(ctx, prefix):
    return [r for r in ctx.reqs if str(r.get("metric", "")).startswith(prefix)]


def _features(ctx, area):
    return [norm_name(r.get("feature")) for r in ctx.features if r.get("area") == area and r.get("feature")]


def _has_feature(option, feat):
    have = " ".join(option.get("features") or []) + " " + norm_name(option.get("name"))
    return all(w in have for w in feat.split()) or feat in have


def build_plan(facts) -> dict:
    ctx = Ctx(facts)
    issues = []
    miss = lambda area, text: issues.append({"level": "missing", "area": area, "text": text})  # noqa: E731
    fail = lambda area, text: issues.append({"level": "fail", "area": area, "text": text})  # noqa: E731
    warn = lambda area, text: issues.append({"level": "warn", "area": area, "text": text})  # noqa: E731
    plan = {"people": {}, "venue": {}, "schedule": {}, "food": {}, "judging": {}, "budget": {}}

    # ------------------------------------------------------------------ people & teams
    students, s_f = _count(ctx, "students")
    staff, st_f = _count(ctx, "staff")
    other_people, o_f = _count(ctx, "other")
    if students is None:
        miss("judging", "number of students not stated")
    teams = None
    if ctx.teams_f and ctx.teams_f.get("count"):
        teams, teams_src = int(ctx.teams_f["count"]), _src(ctx.teams_f)
    elif students is not None and ctx.team_size and ctx.team_size.get("value"):
        teams, teams_src = math.ceil(students / ctx.team_size["value"]), f"{_src(s_f)}/{_src(ctx.team_size)}"
    else:
        teams_src = None
        miss("judging", "number of teams (or team size) not stated")

    # ------------------------------------------------------------------ judging
    judges_listed, j_f = _count(ctx, "judges")
    change = sum(int(f.get("count_change") or 0) for f in ctx.judge_changes)
    judges_avail = None if judges_listed is None else judges_listed + change
    per = ctx.terms.get("max_teams_per_judge")
    mpt = ctx.terms.get("minutes_per_team")
    duration = ctx.duration_f.get("minutes") if ctx.duration_f else None
    if duration is None:
        miss("schedule", "event duration not stated")
    for i, v in enumerate(ctx.venues):
        if v.get("cost") is None:
            if duration is None:
                miss("venue", f"{v['name']} is priced per hour but the event length is unknown")
                ctx.venues[i] = dict(v, cost=None)
            else:
                ctx.venues[i] = dict(v, cost=int(v["cost_per_hour"] * math.ceil(duration / 60)),
                                     priced=f"Rs {v['cost_per_hour']:,}/hour x {math.ceil(duration / 60)} h")
    ctx.venues = [v for v in ctx.venues if v.get("cost") is not None]
    mandatory = [i for i in ctx.items if i.get("minutes")]
    mand_min = sum(int(i["minutes"]) for i in mandatory)
    min_judges = max([int(r["value"]) for r in _reqs(ctx, "judging.judges") if r.get("op") in (">=", "==") and r.get("value")] or [0])

    judges_used = rounds = judging_min = None
    assignment = []
    if teams and mpt and judges_avail is not None and not per:
        per = teams
        warn("judging", "no limit on teams per judge stated - only the time available limits each judge's load")
    if teams and per and mpt and judges_avail is not None:
        needed = max(math.ceil(teams / per), min_judges)
        window = (duration - mand_min) if duration else None
        for k in range(needed, max(judges_avail, needed) + 1):
            r = math.ceil(teams / k)
            if r <= per and (window is None or r * mpt <= window):
                judges_used, rounds = k, r
                break
        if judges_used is None or judges_used > judges_avail:
            fail("judging", f"not enough judges: {teams} teams need at least {needed} judges "
                            f"(max {per} teams each{', judging must fit the event' if window else ''}), only {judges_avail} available")
            judges_used = rounds = None
        else:
            judging_min = rounds * mpt
            for t in range(teams):
                assignment.append({"team": t + 1, "judge": (t % judges_used) + 1, "round": t // judges_used + 1})
    else:
        if judges_avail is None:
            miss("judging", "number of judges not stated")
        if not per or not mpt:
            miss("judging", "judging terms (minutes per team / max teams per judge) not stated")
    plan["judging"] = {"teams": teams, "teams_src": teams_src, "judges_available": judges_avail,
                       "judges_available_src": [_src(j_f)] + [_src(f) for f in ctx.judge_changes if f.get("count_change")],
                       "judges_used": judges_used, "rounds": rounds, "minutes_per_team": mpt,
                       "max_teams_per_judge": per, "judging_minutes": judging_min,
                       "max_load": (max(sum(1 for a in assignment if a["judge"] == j) for j in range(1, judges_used + 1))
                                    if judges_used else None),
                       "assignment": assignment, "terms_src": ctx.terms.get("id")}

    # ------------------------------------------------------------------ people on site
    people = None
    if students is not None and judges_used is not None:
        people = students + (staff or 0) + judges_used + (other_people or 0)
    plan["people"] = {"students": students, "staff": staff, "judges": judges_used, "other": other_people,
                      "on_site": people, "src": [_src(s_f), _src(st_f), _src(o_f)]}
    if staff is None:
        warn("food", "staff count not stated - counted as 0")

    # ------------------------------------------------------------------ food quantity
    qty = people
    for r in _reqs(ctx, "food.quantity"):
        if r.get("op") in (">=", "==") and r.get("value") and qty is not None:
            qty = max(qty, int(r["value"]))
    for o in ctx.orders:
        if o.get("area") == "food" and o.get("quantity") is not None and qty is not None:
            if o["quantity"] < qty:
                fail("food", f"order of {o['quantity']} boxes is below the {qty} people who must be fed "
                             f"({students} students + {staff or 0} staff + {judges_used} judges)")
            qty = max(qty, int(o["quantity"]))

    # ------------------------------------------------------------------ candidates
    v_feats, f_feats = _features(ctx, "venue"), _features(ctx, "food")
    venues_ok, venue_notes = [], []
    for v in ctx.venues:
        why = []
        if people is not None and v["capacity"] < people:
            why.append(f"seats {v['capacity']} < {people} people")
        why += [f"no {ft}" for ft in v_feats if not _has_feature(v, ft)]
        for r in _reqs(ctx, "venue."):
            val = v["capacity"] if r["metric"] == "venue.capacity" else v["cost"]
            if _metric_ok(val, r.get("op"), r.get("value")) is False:
                why.append(f"{r['metric']} {val} not {r['op']} {r['value']}")
        (venue_notes.append({"name": v["name"], "why": why}) if why else venues_ok.append(v))
    foods_ok, food_notes = [], []
    for f in ctx.foods:
        why = [f"not {ft}" for ft in f_feats if not _has_feature(f, ft)]
        for r in _reqs(ctx, "food.price_per_head"):
            if _metric_ok(f["price_per_head"], r.get("op"), r.get("value")) is False:
                why.append(f"price {f['price_per_head']} not {r['op']} {r['value']}")
        (food_notes.append({"name": f["name"], "why": why}) if why else foods_ok.append(f))
    if not ctx.venues:
        miss("venue", "no venue options stated")
    elif people is not None and not venues_ok:
        fail("venue", "no venue meets the requirements: " + "; ".join(f"{n['name']}: {', '.join(n['why'])}" for n in venue_notes))
    if not ctx.foods:
        miss("food", "no food options stated")
    elif not foods_ok:
        fail("food", "no food option meets the requirements")

    for o in ctx.orders:
        target = norm_name(o.get("item"))
        if o.get("area") == "venue" and target:
            hit = [v for v in ctx.venues if norm_name(v["name"]) in target or target in norm_name(v["name"])]
            if hit:
                bad = [n for n in venue_notes if n["name"] == hit[0]["name"]]
                if bad:
                    fail("venue", f"moving to {hit[0]['name']} breaks the rules: {', '.join(bad[0]['why'])}")
                else:
                    venues_ok = [hit[0]]
        if o.get("area") == "food" and target and o.get("quantity") is None:
            hit = [f for f in ctx.foods if norm_name(f["name"]) in target or target in norm_name(f["name"])]
            if hit:
                bad = [n for n in food_notes if n["name"] == hit[0]["name"]]
                if bad:
                    fail("food", f"switching to {hit[0]['name']} breaks the rules: {', '.join(bad[0]['why'])}")
                else:
                    foods_ok = [hit[0]]

    # ------------------------------------------------------------------ budget pieces
    honor = ctx.terms.get("honorarium")
    judges_cost = judges_used * honor if (judges_used is not None and honor is not None) else None
    if judges_used is not None and honor is None:
        warn("budget", "no judge honorarium stated - judges cost Rs 0")
        honor = 0
    committed = [{"item": c.get("item"), "amount": int(c["amount"]), "src": c["id"]}
                 for c in ctx.committed if c.get("amount") is not None]
    approved_opt = [{"item": o.get("item"), "amount": int(o["amount"]), "src": o["id"]}
                    for o in ctx.optional if o.get("approved") and o.get("amount") is not None]
    fixed = sum(c["amount"] for c in committed) + sum(o["amount"] for o in approved_opt) + (judges_cost or 0)
    cap = ctx.cap_f.get("amount") if ctx.cap_f else None
    if cap is None:
        miss("budget", "budget cap not stated")

    # ------------------------------------------------------------------ choose venue + food
    best = None
    if venues_ok and foods_ok and qty is not None:
        combos = []
        for fi, f in enumerate(foods_ok):
            for v in venues_ok:
                food_cost = f["price_per_head"] * qty + int(f.get("fixed_cost") or 0)
                total = v["cost"] + food_cost + fixed
                ok = cap is None or total <= cap
                for r in _reqs(ctx, "budget.total") + _reqs(ctx, "food.cost"):
                    val = total if r["metric"] == "budget.total" else food_cost
                    ok = ok and _metric_ok(val, r.get("op"), r.get("value")) is not False
                combos.append((not ok, fi, v["cost"], total, v, f, food_cost))
        combos.sort(key=lambda c: c[:4])
        best = combos[0]
        if best[0]:
            fail("budget", f"over budget: cheapest feasible plan costs Rs {min(c[3] for c in combos):,} "
                           f"but the cap is Rs {cap:,}")
    _, _, _, total, venue, food, food_cost = best if best else (None,) * 7

    plan["venue"] = {"chosen": venue and {"name": venue["name"], "capacity": venue["capacity"], "cost": venue["cost"],
                                          "features": venue.get("features") or [], "src": venue["id"]},
                     "required_features": v_feats, "people_on_site": people,
                     "alternatives": [{"name": v["name"], "capacity": v["capacity"], "cost": v["cost"],
                                       "why_not": "more expensive" if venue and v is not venue else ""}
                                      for v in venues_ok if v is not venue] +
                                     [{"name": n["name"], "why_not": ", ".join(n["why"])} for n in venue_notes] +
                                     [{"name": u["name"], "why_not": "not available"} for u in ctx.unavailable
                                      if u["kind"] == "venue_option"]}
    plan["food"] = {"chosen": food and {"name": food["name"], "price_per_head": food["price_per_head"],
                                        "fixed_cost": int(food.get("fixed_cost") or 0), "src": food["id"]},
                    "quantity": qty, "cost": food_cost, "required_features": f_feats,
                    "alternatives": [{"name": f["name"], "price_per_head": f["price_per_head"],
                                      "would_cost": f["price_per_head"] * qty + int(f.get("fixed_cost") or 0) if qty else None}
                                     for f in foods_ok if f is not food] +
                                    [{"name": n["name"], "why_not": ", ".join(n["why"])} for n in food_notes],
                    "rule": "keep the menu that was quoted first (at its latest price) unless the budget forces a cheaper one"}

    # ------------------------------------------------------------------ schedule
    plan["schedule"] = _schedule(ctx, duration, mandatory, judging_min, fail, warn)

    # ------------------------------------------------------------------ budget
    lines = []
    if venue:
        lines.append({"item": f"Venue: {venue['name']}", "amount": venue["cost"], "src": venue["id"]})
    if food:
        lines.append({"item": f"Food: {qty} x {food['name']} @ Rs {food['price_per_head']:,}"
                      + (f" + Rs {int(food['fixed_cost']):,} fixed charge" if food.get("fixed_cost") else ""),
                      "amount": food_cost, "src": food["id"]})
    if judges_cost is not None:
        lines.append({"item": f"Judges: {judges_used} x Rs {honor:,} honorarium", "amount": judges_cost,
                      "src": ctx.terms.get("honorarium_src")})
    lines += [{"item": f"Already ordered: {c['item']}", "amount": c["amount"], "src": c["src"]} for c in committed]
    lines += [{"item": f"Approved extra: {o['item']}", "amount": o["amount"], "src": o["src"]} for o in approved_opt]
    total_sum = sum(l["amount"] for l in lines)
    remaining = (cap - total_sum) if cap is not None else None
    not_inc = [{"item": o.get("item"), "amount": o.get("amount"), "src": o["id"],
                "note": ("would fit in the remaining budget if approved" if remaining is not None and o.get("amount") is not None
                         and o["amount"] <= remaining else "would NOT fit in the remaining budget")}
               for o in ctx.optional if not o.get("approved")]
    plan["budget"] = {"lines": lines, "total": total_sum, "cap": cap, "cap_src": _src(ctx.cap_f),
                      "remaining": remaining, "not_included": not_inc}
    if cap is not None and total_sum > cap and not any(i["level"] == "fail" and i["area"] == "budget" for i in issues):
        fail("budget", f"total Rs {total_sum:,} exceeds cap Rs {cap:,}")

    # ------------------------------------------------------------------ generic requirements
    metrics = {
        "venue.capacity": venue and venue["capacity"], "venue.cost": venue and venue["cost"],
        "food.quantity": qty, "food.price_per_head": food and food["price_per_head"], "food.cost": food_cost,
        "judging.judges": judges_used, "judging.teams_per_judge": plan["judging"]["max_load"],
        "schedule.minutes": plan["schedule"].get("total_minutes"), "budget.total": total_sum,
    }
    plan["requirements"] = []
    for r in ctx.reqs:
        ok = _metric_ok(metrics.get(r.get("metric")), r.get("op"), r.get("value"))
        state = "PASS" if ok else ("FAIL" if ok is False else "UNVERIFIED")
        plan["requirements"].append({"rule": f"{r.get('metric')} {r.get('op')} {r.get('value')}",
                                     "actual": metrics.get(r.get("metric")), "state": state, "src": r["id"]})
        if ok is False:
            fail(str(r.get("metric", "budget")).split(".")[0], f"requirement {r.get('metric')} {r.get('op')} {r.get('value')} "
                                                               f"not met (actual {metrics.get(r.get('metric'))})")
    for ft in v_feats + f_feats:
        plan["requirements"].append({"rule": f"must have: {ft}", "state": "PASS" if (venue or food) else "UNVERIFIED"})
    for o in ctx.others:
        plan["requirements"].append({"rule": o.get("text"), "area": o.get("area"), "state": "UNVERIFIED", "src": o["id"]})
        warn(o.get("area") or "schedule", f"rule not checked automatically, review by hand: \"{o.get('text')}\" ({o['id']})")

    # ------------------------------------------------------------------ risks (tentative info)
    plan["risks"] = []
    for f in [x for x in facts if x.get("info_only")]:
        if f["kind"] == "judge_change" and f.get("delay_minutes"):
            js = plan["schedule"].get("judging_start")
            spare = (judges_avail - judges_used) if (judges_avail is not None and judges_used) else 0
            plan["risks"].append({"src": f["id"], "text": f"a judge may be {f['delay_minutes']} min late: judging starts at "
                                  f"minute {js}, so the delay does not affect it" if js is not None and js >= f["delay_minutes"]
                                  else f"a judge may be {f['delay_minutes']} min late; {spare} spare judge(s) can cover"})
    plan["issues"] = issues
    return plan


def _schedule(ctx, duration, mandatory, judging_min, fail, warn):
    out = {"total_minutes": duration, "start": ctx.start_f.get("time") if ctx.start_f else None, "slots": []}
    if duration is None:
        return out
    j = judging_min or 0
    fixed, floating = [], []
    start_min = None
    if out["start"]:
        h, m = map(int, out["start"].split(":"))
        start_min = h * 60 + m
    for it in mandatory:
        if it.get("at") and start_min is not None:
            h, m = map(int, it["at"].split(":"))
            fixed.append((h * 60 + m - start_min, int(it["minutes"]), it))
        else:
            floating.append(it)
    slots = []
    for off, mins, it in fixed:
        if off < 0 or off + mins > duration:
            fail("schedule", f"'{it['name']}' at {it['at']} falls outside the event")
        slots.append({"start": off, "end": off + mins, "name": it["name"], "type": "required", "src": it["id"]})
    slots.sort(key=lambda s: s["start"])
    for a, b in zip(slots, slots[1:]):
        if b["start"] < a["end"]:
            fail("schedule", f"'{a['name']}' overlaps '{b['name']}'")
    rounds = ctx.terms.get("minutes_per_team") and j // ctx.terms["minutes_per_team"]
    if j and rounds:
        mpt, end, placed = ctx.terms["minutes_per_team"], duration, 0
        while placed < rounds and end - mpt >= 0:
            clash = [x for x in slots if x["start"] < end and x["end"] > end - mpt]
            if clash:
                end = min(x["start"] for x in clash)
                continue
            slots.append({"start": end - mpt, "end": end, "name": f"Judging round {rounds - placed}", "type": "judging"})
            end -= mpt
            placed += 1
        if placed < rounds:
            fail("schedule", f"only {placed} of {rounds} judging rounds fit in the event")
        slots.sort(key=lambda s: s["start"])
    # gaps -> place floating mandatory items in the middle of the largest gap, rest is building time
    for it in floating:
        gaps = _gaps(slots, duration)
        if not gaps:
            fail("schedule", f"no time left for '{it['name']}'")
            continue
        g0, g1 = max(gaps, key=lambda g: g[1] - g[0])
        mins = int(it["minutes"])
        if g1 - g0 < mins:
            fail("schedule", f"no room for '{it['name']}' ({mins} min)")
            continue
        s = g0 + ((g1 - g0) - mins) // 2
        slots.append({"start": s, "end": s + mins, "name": it["name"], "type": "required", "src": it["id"]})
        slots.sort(key=lambda s: s["start"])
    for g0, g1 in _gaps(slots, duration):
        slots.append({"start": g0, "end": g1, "name": "Building (teams work on projects)", "type": "build"})
    slots.sort(key=lambda s: s["start"])
    if start_min is not None:
        for s in slots:
            s["clock"] = f"{_clock(start_min + s['start'])}-{_clock(start_min + s['end'])}"
    covered = sum(s["end"] - s["start"] for s in slots)
    if covered != duration:
        fail("schedule", f"slots cover {covered} min but the event is {duration} min")
    out["slots"] = slots
    js = [x["start"] for x in slots if x["type"] == "judging"]
    out["judging_start"] = min(js) if js else None
    out["build_minutes"] = sum(s["end"] - s["start"] for s in slots if s["type"] == "build")
    if out["build_minutes"] == 0:
        warn("schedule", "no building time left")
    return out


def _gaps(slots, duration):
    gaps, t = [], 0
    for s in sorted(slots, key=lambda s: s["start"]):
        if s["start"] > t:
            gaps.append((t, s["start"]))
        t = max(t, s["end"])
    if t < duration:
        gaps.append((t, duration))
    return gaps


def _clock(m):
    h, mi = divmod(int(m) % (24 * 60), 60)
    return f"{h:02d}:{mi:02d}"
