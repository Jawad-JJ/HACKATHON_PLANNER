Test-only data. Never imported by production code (`planforge/`, `main.py`, `serve.py`).

- `*_extraction.json`: hand-written examples of what the reading model should return for the
  matching `samples/*.txt` input. Tests feed them through a scripted transport so the planner,
  gate and trace can be checked without network access. They are NOT recorded model output,
  and their `usage` numbers are labelled test values.
