# HACKATHON_PLANNER: PlanForge AI

Mind to Machine Hackathon (18 Nov 2026). Reads a pack of messages (emails, WhatsApp texts, notices, in
English and Roman Urdu) and plans a 4-hour hackathon: **venue, schedule, food, judging, budget**.
A small model reads the messages (**one `reading` call per run**). Plain Python does all planning,
arithmetic and checking. Every message, first pack or later update, goes through **the same command**.

```
python main.py <messages.txt>
```

- **No packages needed:** Python 3.10+ standard library only (works even with Windows Smart App Control).
- **Trace:** every call is numbered, with model, area tag, exact input/output, tokens *as reported* and the total at the end.
- **Wrong messages:** rejected with the broken rule as the reason; the last valid plan is kept.
- **Updates:** the prediction is saved before the call; the run prints whether it `MATCHED`.

## Setup (2 minutes)

```powershell
git clone https://github.com/Jawad-JJ/HACKATHON_PLANNER.git
cd HACKATHON_PLANNER
copy .env.example .env      # add your key; pick a model from the organizers' small-model list
python scripts/check_model.py
```

## Use

```powershell
python main.py samples/sample_pack.txt                  # full pack -> new plan (+ trace)
python main.py samples/practice_change_printing.txt     # update: printing 10,000 -> 15,000
python main.py samples/practice_wrong_caterer.txt       # wrong: 100 boxes -> rejected with reason
python serve.py                                         # dashboard at http://127.0.0.1:8000
python desktop.py                                       # same dashboard in its own app window
```

A file with 4 or more text blocks (a pack) starts a new plan automatically; the previous session is
archived in `state/archive/`. A file with one message updates the current plan. Saved after every run, in
`outputs/`: `submission.txt` (plan + rejected messages + full trace), `latest_plan.txt/.json`,
`full_trace.txt/.json`, `rejections.json`, `updates.json`.

`state/` and `outputs/` are gitignored, so `git status` stays clean after runs.

## Test day checklist

1. `git status` is clean and `git log -1` matches the submitted hash.
2. `python main.py <unseen_pack.txt>`
3. For each new message: save it as a `.txt` file, then `python main.py <message.txt>`
4. Prediction slip: **"Only reading makes a model call (1 call). Venue, schedule, food, judging, budget: none."**
5. Upload `outputs/submission.txt`.

## Live results (team laptop, 18 Nov, gemini-3.5-flash-lite)

| Run | Calls | Tokens (as reported) | Time | Result |
|---|---|---|---|---|
| Sample pack | 1 `reading` | 1,043 in + 670 out = 1,713 | 2.3 s | VALID: 177 people, Hall A, standard box Rs 1,200, Rs 547,400 |
| Printing 10,000 -> 15,000 | 1 `reading` | 677 | 1-16 s | VALID: replaced, total Rs 552,400 |
| Caterer "100 boxes" | 1 `reading` | 675 | 1.1 s | REJECTED: below the 177 people who must be fed; plan stays VALID |

Under load the API once answered `503 high demand`; the run retried on `gemini-3.1-flash-lite` and both calls
appear in the trace.

## Tests

```powershell
python -m unittest discover -s tests -t .      # 35 tests, no network needed
```

They cover the sample pack (177 people, Hall A, Rs 1,200 box, Rs 547,400), both practice messages,
a self-written unseen-style pack (wheelchair access, Asr break at a fixed time, halal food, a changed
headcount, a wrong venue move), supplier authority, failed and unusable model output, the fallback model,
and trace honesty. Test fixtures are hand-written and used only by tests.

## Web / mobile / laptop

- `python serve.py`: local API + dashboard, using the **same** `pipeline.run` as the CLI. `HOST=0.0.0.0` to open it from a phone on the same Wi-Fi.
- **PWA:** use "Install app" in Chrome/Edge (laptop) or "Add to Home screen" (phone).
- **Vercel:** hosts `web/` as a static PWA (see `vercel.json`). It connects to a running laptop backend, or opens an exported `outputs/session.json` read-only. Keys and state never leave the laptop.

Docs: `docs/TEST_DAY.md` (runbook) · `docs/TEAM_GUIDE.md` (how to defend each part) · `docs/TRACEABILITY.md` (brief -> code -> test).
