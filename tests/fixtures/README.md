Test-only data. Never imported by production code (`planforge/`, `main.py`, `serve.py`).

- `*_extraction.json`: hand-written examples of what the reading model should return for the
  matching `samples/*.txt` input. Tests feed them through a scripted transport so the planner,
  gate and trace can be checked without network access. They are NOT recorded model output,
  and their `usage` numbers are labelled test values.
- `recorded_*_output.txt`: REAL model outputs copied from the team's first live run on 18 Nov
  (gemini-3.5-flash-lite / gemini-3.1-flash-lite), used as regression tests for real-model quirks
  (e.g. `duration {"value": 240}` instead of `minutes`, list-wrapped JSON).
