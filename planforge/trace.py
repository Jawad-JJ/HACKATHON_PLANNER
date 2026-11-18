"""Trace of every real model call: number, model, area tag, exact input/output, reported tokens.

Token counts are copied verbatim from the provider's `usage` object. If the provider does not
report a count we store None and print `unreported` - we never estimate.
"""
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import TAGS


@dataclass
class CallRecord:
    number: int                 # global, monotonic across the whole session
    run_id: int
    tag: str                    # exactly one of TAGS
    model: str                  # model name as returned by the provider (falls back to configured)
    request: list               # exact messages sent (system + user)
    response: str               # exact text received, or "" on error
    status: str                 # ok | error
    error: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usage_raw: dict = field(default_factory=dict)
    seconds: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if self.tag not in TAGS:
            raise ValueError(f"invalid area tag {self.tag!r}")


def to_dict(rec: CallRecord) -> dict:
    return asdict(rec)


def from_dict(d: dict) -> CallRecord:
    return CallRecord(**d)


def token_totals(calls) -> dict:
    """Sum of provider-reported counts. A call with an unreported count is listed separately."""
    tot = {"input": 0, "output": 0, "total": 0, "calls": 0, "unreported_calls": 0}
    for c in calls:
        c = c if isinstance(c, dict) else to_dict(c)
        tot["calls"] += 1
        if c.get("total_tokens") is None and c.get("input_tokens") is None:
            tot["unreported_calls"] += 1
            continue
        tot["input"] += c.get("input_tokens") or 0
        tot["output"] += c.get("output_tokens") or 0
        tot["total"] += c.get("total_tokens") if c.get("total_tokens") is not None else \
            (c.get("input_tokens") or 0) + (c.get("output_tokens") or 0)
    return tot
