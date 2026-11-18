# Team guide: defend every part of PlanForge AI

**One sentence:** a small model *reads* the messages once; plain Python *plans, checks and explains*; every
message passes the same gate, and the trace shows every real model call with the tokens the provider reported.

## The pipeline (same for the first pack and every new message)

```
python main.py <file>
  1 ingest.py    read the file exactly, SHA-256, cut into numbered blocks          (no model)
  2 pipeline.py  new pack or update? write the PREDICTION to disk                  (no model)
  3 reader.py    ONE call, tag "reading": blocks -> typed facts as JSON            (model)
  4 gate.py      each message in date order: lane? quote/maybe? outdated? breaks the plan?   (no model)
  5 ledger.py    newest fact per identity wins; older ones kept as superseded      (no model)
  6 planner.py   venue, schedule, food, judging, budget                            (no model)
  7 validate.py  the six checks from the brief                                     (no model)
  8 render.py    print plan + trace + reasons + token totals; save outputs/        (no model)
```

## What each part is for, and what breaks without it

| Part | Purpose | Without it |
|---|---|---|
| `ingest.py` | Keeps the exact text + hash; the model returns *block numbers*, not retyped text | Evidence could be paraphrased; can't prove what the message said |
| `reader.py` | The only language step: English/Roman Urdu -> typed facts (`food_option`, `budget_cap`, ...) | Code would need hard-coded phrases ("ab ... hoga") -> breaks on new wording |
| `llm.py` | The single door to any model; records every attempt, copies `usage` verbatim | A call could escape the trace -> false trace = disqualification |
| `trace.py` | Call number, model, one of 6 tags, exact input/output, reported tokens; `unreported` if missing | No proof of tokens/models/areas |
| `ledger.py` | Newest fact wins per identity (same box price, same bill); sender lanes | Rs 1,000 and Rs 1,200 both counted; printing counted twice; caterer could change our headcount |
| `gate.py` | Every message: irrelevant / outside lane / quote-only / outdated / *re-plan and reject if it creates a new hard failure* | The wrong message would be applied and the plan would become invalid |
| `planner.py` | Arithmetic and choices in code: judges needed, people on site, cheapest venue that fits, timeline, budget | A model doing arithmetic -> wrong totals and many more tokens |
| `validate.py` | Six checks recomputed independently | We could print a plan that silently fails a check |
| `session.py` | Atomic save of messages, facts, plan, trace | Updates would forget the first run; a crash could corrupt state |
| `serve.py` + `web/` | Dashboard/PWA calling the same `pipeline.run` | UI marks lost; no separate logic to defend |

## Key decisions (and why)

1. **Model only for reading.** The brief: "use a model where language needs reading, and plain code where arithmetic will do." One call per run -> lowest tokens, fastest, and the prediction is always right.
2. **Judges used = fewest that cover all teams** within max-teams-per-judge and the time left after required breaks. Sample: 50 teams / 3 = 17 judges -> 150 + 10 + 17 = **177 people to feed** (matches the brief's note).
3. **People on site = students + staff + judges used** -> venue must seat them, food must feed them.
4. **Venue = cheapest that seats everyone and has every required feature.** A generator is only required if a message says so.
5. **Food = the menu quoted first, at its latest price**, unless the budget forces a cheaper one (cheaper options are shown with what they would cost).
6. **Quotes and requests are not approved spending** (DJ shown as "not included, would fit if approved").
7. **"May be late" is a risk, not an absence.** Judging is at the end, so a 10-minute delay doesn't matter.
8. **Corrections replace, never add** (printing 10,000 -> 15,000 = +5,000).
9. **A wrong message is rejected because it would break a hard rule**, with that rule as the printed reason (100 boxes < 177 people).

## Likely judge questions

- **Why only a "reading" call? Where are the area calls?** Areas are pure arithmetic and rules, so they run in code with 0 tokens. "Only affected areas made model calls" is satisfied: no area makes calls; only the language step does.
- **How do you know the tokens are right?** We copy `prompt_tokens`, `completion_tokens`, `total_tokens` from the provider's `usage` object. We never estimate; a missing count prints `unreported`.
- **How do you catch the wrong message?** Every new fact is tried on a copy of the plan. If it creates a new hard failure (under-feeding, venue too small or missing a required feature, over budget, not enough judges, schedule overflow) it's rejected, and the failure is the reason. Older-dated facts are "outdated". Suppliers can't change things outside their lane.
- **New kind of constraint?** The reader maps it to a metric rule (`venue.capacity >= 220`, `budget.total <= ...`) or a feature rule (venue must be wheelchair accessible, food must be halal); the planner filters options. Anything else is listed as `UNVERIFIED` for a human. It's never silently passed.
- **What if the model output is broken?** One retry (or the fallback model); both calls are traced. If it still fails, the previous valid plan is kept and the run reports the error.
- **How is the sample pack not hard-coded?** `planforge/` contains no pack numbers or messages; facts come only from the input file. Tests use separate fixtures and a self-written pack with different numbers.
- **Prediction slip?** Always: *"Only `reading` will make a model call (1 call). Venue, schedule, food, judging and budget make no model calls."* The run saves the prediction before calling and prints `MATCHED`.

## Who owns what (everyone must be able to explain all of it)

- **Member 1, language & evidence:** ingest, reader prompt, ledger chronology, sender lanes, outdated messages.
- **Member 2, planning & correctness:** planner (5 areas), validate (6 checks), gate rejection logic.
- **Member 3, interface & audit:** llm adapter, trace/tokens, exports, dashboard/PWA, tests, git hygiene.
