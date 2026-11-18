# Test day runbook (1:30 test run)

## Before the volunteer arrives
1. `python scripts/check_model.py`: the key works and a call returns usage numbers.
2. `git status` shows nothing; `git log -1` shows the submitted hash. (Runs only write to the gitignored `state/` and `outputs/`.)
3. Keep one PowerShell window open in the repo folder, and the dashboard (`python serve.py`) in a second window if you want the UI.

## The run
| Step | Do | Expect |
|---|---|---|
| Unseen pack released | Save it as `pack.txt`, then run `python main.py pack.txt` | `new pack`, 1 call tagged `reading`, plan VALID, six PASS lines |
| Each new message | Save the text as `m1.txt` (then `m2.txt`, `m3.txt`); run `python main.py m1.txt` | `update`, 1 call, decisions show ACCEPTED / REJECTED with a reason |
| Prediction slip | Write: **"Only `reading` will make a model call (1 call). Venue, schedule, food, judging and budget will make no model calls."** | The run prints `prediction MATCHED` |
| Upload | `outputs/submission.txt` (plan + rejected messages + full trace + total tokens) | |

The message that is "plausible but wrong" shows as **REJECTED** with the broken rule (e.g. too few meals,
venue too small or missing a required feature, over budget, sender outside its authority, older than a fact we
already have). The plan stays VALID.

## If something goes wrong
| Symptom | Meaning / action |
|---|---|
| `Model not configured` | `.env` missing or empty: `copy .env.example .env` and fill it in |
| Call shows `status: error` and a second call appears | The primary model failed and the fallback model was used; both are in the trace (that's correct) |
| `RUN FAILED ... previous plan kept` | Both calls failed (network or quota). Fix the key/network and run the same command again |
| Plan NOT VALID after the pack | Read the FAIL lines: usually a fact the pack never states (e.g. no budget). Tell the judge exactly that; don't edit code |
| A rule shows `UNVERIFIED` | The model found a rule the code can't check automatically; it is listed for a human. Mention it to the judge |

Never edit code after 1:25. Everything else is inputs and `.env`.
