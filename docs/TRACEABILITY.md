# Requirements traceability matrix

Official brief (Mind to Machine Hackathon, 18 Nov 2026) takes precedence over the proposal.

| # | Requirement (source) | Where it is implemented | How it is verified |
|---|---|---|---|
| R1 | Read every message from a text file, exactly as given; no facts typed into code (brief §1) | `planforge/ingest.py` keeps raw bytes, SHA-256 and exact block text; reader returns block numbers, never rewritten text | `tests/test_ingest.py`, grep shows no pack numbers in `planforge/` |
| R2 | Every message through the same command, no flags/hints/edits (brief §2) | `main.py <file>` only; pack vs update decided from session state + what the reader finds | `tests/test_pipeline.py` runs pack and updates through `run_file()` |
| R3 | Trace: every call numbered, model name, one area tag, input, output, reported tokens, total at end (brief §3) | `planforge/llm.py` (single instrumented adapter), `planforge/trace.py`, `planforge/render.py` | `tests/test_trace.py` (usage copied verbatim, `unreported` when missing) |
| R4 | Accept new messages and update the existing plan (brief §4) | `planforge/pipeline.py` + `planforge/session.py` (atomic JSON) | practice-update tests |
| R5 | Conflicting message: keep plan valid, print reason in trace (brief §5) | `planforge/gate.py`: authority check, chronology, re-plan-and-validate gate | wrong-message test (100 boxes) |
| R6 | Full run <= 2 min; update <= 5 model calls and <= 1 min (Limits) | One `reading` call per run (max 2 with one repair retry); deadlines in `planforge/pipeline.py` | call-count assertions in tests; timing printed every run |
| R7 | Five areas: venue, schedule, food, judging, budget; respect every constraint incl. unseen kinds | `planforge/planner.py`, generic metric/feature requirements, `other` rules flagged UNVERIFIED | sample + synthetic unseen-pack tests |
| R8 | Six output checks: figures, budget, venue fits, schedule valid, enough judges, all areas | `planforge/validate.py` | asserted in tests |
| R9 | Only affected areas make model calls; written prediction matches | Areas are computed in code (0 calls); prediction printed and saved **before** the call | `updates.json`, test asserts prediction == actual |
| R10 | Fewer tokens | One compact reading call per run; arithmetic in code; no per-area LLM agents | token totals printed |
| R11 | UI shows plan, trace, rejected messages | `web/` dashboard served by `serve.py` (same pipeline) + PWA | manual check |
| R12 | Save final plan and full trace to a file | `outputs/submission.txt`, `latest_plan.*`, `full_trace.*` | produced on every run |
| R13 | git status clean; no changes after freeze | `state/` and `outputs/` gitignored | `git status --porcelain` after runs |
