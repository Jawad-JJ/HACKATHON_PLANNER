"""Fact ledger: which facts are active, which were superseded, and who may change what.

Rules (plain code, explainable):
  * Same fact identity (e.g. the price of the same lunch box, the same committed bill) -> the most
    recent one wins: compare message dates when both are dated, otherwise arrival order.
  * A supplier/participant may only state facts in its own lane (a caterer can quote food, not
    change the headcount or our order size); organizer/finance/judging/other are not restricted.
  * Quotes/requests ("proposed") and "tentative" facts are recorded but never change the plan.
"""
import re
from datetime import date, datetime

from .reader import norm_name

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# kinds each restricted role may state; roles not listed may state anything
LANES = {
    "venue": {"venue_option", "order_change", "optional_cost", "other"},
    "caterer": {"food_option", "order_change", "optional_cost", "other"},
    "judge": {"judge_change", "other"},
    "student": {"optional_cost", "other"},
}
# kinds that only ever inform (never applied as facts)
INFO_STATUSES = {"proposed", "tentative"}
ALWAYS_PROPOSAL = {"optional_cost"}


def parse_date(raw, default_year=None):
    """'9 Nov', 'Nov 9', '2026-11-09', '09/11/2026', '12 November' -> date | None."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    year = default_year or date.today().year
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*(?:\s+(\d{4}))?", s) or \
        re.search(r"([a-z]{3})[a-z]*\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?", s)
    if not m:
        return None
    a, b, y = m.group(1), m.group(2), m.group(3)
    day, mon = (a, b) if a.isdigit() else (b, a)
    if mon[:3] not in MONTHS:
        return None
    try:
        return date(int(y) if y else year, MONTHS[mon[:3]], int(day))
    except ValueError:
        return None


def newer(a: dict, b: dict) -> bool:
    """Is fact a more recent than fact b?"""
    da, db = a.get("date_iso"), b.get("date_iso")
    if da and db and da != db:
        return da > db
    return a["order"] > b["order"]


def key(f: dict):
    k = f["kind"]
    if k == "headcount":
        return (k, norm_name(f.get("role")))
    if k in ("venue_option", "food_option"):
        return (k, norm_name(f.get("name")))
    if k in ("committed_cost", "optional_cost"):
        return (k, norm_name(f.get("item")))
    if k == "schedule_item":
        return (k, norm_name(f.get("name")))
    if k == "requirement":
        return (k, f.get("metric"), f.get("op"))
    if k == "feature_requirement":
        return (k, f.get("area"), norm_name(f.get("feature")))
    if k == "order_change":
        return (k, f.get("area"), norm_name(f.get("item")))
    if k in ("team_size", "teams", "duration", "start_time", "budget_cap", "judge_terms"):
        return (k,)
    return (k, f["id"])  # judge_change, other: each one stands alone


def same_item(a: str, b: str) -> bool:
    """'printing' vs 'printing bill' -> True (token containment), so corrections match."""
    ta, tb = set(norm_name(a).split()) - {"bill", "the", "cost", "of"}, set(norm_name(b).split()) - {"bill", "the", "cost", "of"}
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def canonical(f: dict, facts: list) -> tuple:
    """Key, but fuzzy-matched to an existing key for named items (e.g. 'printing bill' -> 'printing')."""
    k = key(f)
    if f["kind"] in ("committed_cost", "optional_cost", "food_option", "venue_option", "schedule_item") and len(k) == 2:
        for g in facts:
            gk = g.get("key")
            if gk and gk[0] == k[0] and gk != list(k) and same_item(gk[1], k[1]):
                return tuple(gk)
    return k


def lane_problem(role: str, kind: str) -> str:
    allowed = LANES.get(role)
    if allowed is not None and kind not in allowed:
        return f"a {role} message cannot set '{kind}' (outside its authority)"
    return ""


def active_facts(facts: list) -> list:
    """Accepted, applicable facts with superseded ones removed (latest per key wins)."""
    best = {}
    for f in facts:
        if f.get("state") not in ("active", "superseded") or f["kind"] == "judge_terms":
            continue
        k = tuple(f["key"])
        if k not in best or newer(f, best[k]):
            best[k] = f
    first = {}
    for f in facts:
        if f.get("state") in ("active", "superseded"):
            k = tuple(f["key"])
            first[k] = min(first.get(k, (f.get("date_iso") or "9999", f["order"])), (f.get("date_iso") or "9999", f["order"]))
    out = []
    for k, f in best.items():
        g = dict(f)
        g["first_order"] = first[k]
        out.append(g)
    # judge_terms merge field by field in time order
    terms = sorted([f for f in facts if f["kind"] == "judge_terms" and f.get("state") in ("active", "superseded")],
                   key=lambda f: (f.get("date_iso") or "", f["order"]))
    if terms:
        merged = {"kind": "judge_terms", "id": "+".join(t["id"] for t in terms)}
        for t in terms:
            for fld in ("honorarium", "minutes_per_team", "max_teams_per_judge"):
                if t.get(fld) is not None:
                    merged[fld] = t[fld]
                    merged[fld + "_src"] = t["id"]
        out.append(merged)
    return out


def mark_superseded(facts: list) -> None:
    """Recompute active/superseded labels after any change, with the reason."""
    act = {f["id"] for f in active_facts(facts)}
    latest = {}
    for f in facts:
        if f.get("state") in ("active", "superseded") and f["kind"] != "judge_terms":
            k = tuple(f["key"])
            if k not in latest or newer(f, latest[k]):
                latest[k] = f
    for f in facts:
        if f.get("state") in ("active", "superseded") and f["kind"] != "judge_terms":
            if f["id"] in act:
                f["state"], f["reason"] = "active", f.get("reason") if f.get("state") == "active" else ""
            else:
                w = latest[tuple(f["key"])]
                f["state"] = "superseded"
                f["reason"] = f"replaced by newer {w['id']} ({w.get('date_raw') or 'later message'})"
