"""The six output checks from the brief, recomputed independently from the plan."""
import re


def checks(plan: dict) -> list:
    iss = plan.get("issues", [])
    fails = lambda area: [i["text"] for i in iss if i["level"] == "fail" and i["area"] == area]  # noqa: E731
    missing = [i["text"] for i in iss if i["level"] == "missing"]
    b, v, s, j, f, p = (plan.get(k, {}) for k in ("budget", "venue", "schedule", "judging", "food", "people"))
    out = []

    # 1 correct figures: recompute every sum independently
    errs = []
    if b.get("lines") is not None and sum(l["amount"] for l in b["lines"]) != b.get("total"):
        errs.append("budget lines do not add up")
    if f.get("chosen") and f.get("quantity") is not None and f.get("cost") != int(round(f["chosen"]["price_per_head"] * f["quantity"] * (1 + (f["chosen"].get("service_pct") or 0) / 100))) + f["chosen"].get("fixed_cost", 0):
        errs.append("food cost != price x quantity")
    if p.get("on_site") is not None and p["on_site"] != sum(x or 0 for x in (p["students"], p["staff"], p.get("volunteers"), p["judges"], p["other"])):
        errs.append("headcount does not add up")
    if f.get("quantity") is not None and p.get("on_site") is not None and f["quantity"] < p["on_site"]:
        errs.append("fewer meals than people on site")
    out.append(("Correct figures", not errs and not missing, "; ".join(errs + missing) or
                f"{p.get('on_site')} people on site, {f.get('quantity')} meals, total Rs {b.get('total', 0):,}"))

    # 2 within budget
    ok = b.get("cap") is not None and b.get("total", 0) <= b["cap"] and not fails("budget")
    out.append(("Within budget", ok, f"Rs {b.get('total', 0):,} of Rs {b['cap']:,} (Rs {b['remaining']:,} left)"
                if b.get("cap") is not None else "no budget cap"))

    # 3 venue fits
    ch = v.get("chosen")
    ok = bool(ch) and v.get("people_on_site") is not None and ch["capacity"] >= v["people_on_site"] and not fails("venue")
    out.append(("Venue fits", ok, f"{ch['name']} seats {ch['capacity']} >= {v.get('people_on_site')} people"
                if ch else ("; ".join(fails("venue")) or "no venue chosen")))

    # 4 schedule valid
    slots = s.get("slots") or []
    covered = sum(x["end"] - x["start"] for x in slots)
    ok = bool(slots) and covered == s.get("total_minutes") and not fails("schedule") and \
        all(a["end"] <= b2["start"] for a, b2 in zip(slots, slots[1:]))
    out.append(("Schedule valid", ok, f"{len(slots)} slots cover {covered}/{s.get('total_minutes')} min, no overlaps"
                if ok else ("; ".join(fails("schedule")) or "schedule incomplete")))

    # 5 enough judges
    a = j.get("assignment") or []
    ok = bool(a) and j.get("teams") == len(a) and j.get("judges_used") is not None and \
        j["judges_used"] <= (j.get("judges_available") or 0) and (j.get("max_load") or 0) <= (j.get("max_teams_per_judge") or 0) \
        and not fails("judging")
    out.append(("Enough judges", ok, f"{j.get('judges_used')} of {j.get('judges_available')} judges, "
                f"<= {j.get('max_load')} teams each, all {j.get('teams')} teams assigned" if ok else
                ("; ".join(fails("judging")) or "judging incomplete")))

    # 6 all areas covered
    covered_areas = [n for n, ok in (("venue", bool(ch)), ("schedule", bool(slots)), ("food", bool(f.get("chosen"))),
                                     ("judging", bool(a)), ("budget", b.get("cap") is not None)) if ok]
    out.append(("All areas covered", len(covered_areas) == 5, ", ".join(covered_areas) or "none"))
    return [{"check": n, "pass": bool(ok), "detail": d} for n, ok, d in out]


def is_valid(plan: dict) -> bool:
    return all(c["pass"] for c in checks(plan)) and not any(i["level"] == "fail" for i in plan.get("issues", []))


def fail_set(plan: dict) -> set:
    """Hard failures only (missing data is not a conflict)."""
    return {(i["area"], re.sub(r"\d[\d,]*", "#", i["text"])) for i in plan.get("issues", []) if i["level"] == "fail"}
