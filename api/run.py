"""Vercel serverless function: the SAME pipeline as `python main.py <file>`, in the cloud.

GET  /api/run                          -> {"configured": bool, "model": ...}   (health check)
POST /api/run {"text", "filename", "session"} -> runs the text through pipeline.run and returns the
     updated session, the run record and the submission text.

The server keeps nothing between requests: the browser sends its current session back each time, so
every visitor has their own plan. The model key lives in Vercel's environment variables.
"""
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planforge.config import fallback_config, model_config  # noqa: E402
from planforge.ingest import from_text  # noqa: E402
from planforge.llm import LLMClient  # noqa: E402
from planforge.pipeline import run  # noqa: E402
from planforge.render import submission_text  # noqa: E402
from planforge.session import save  # noqa: E402
from planforge.trace import token_totals  # noqa: E402

MAX_TEXT = 60_000


def process(body: dict) -> tuple:
    text = str(body.get("text") or "")
    if not text.strip():
        return 400, {"error": "empty message file"}
    if len(text) > MAX_TEXT:
        return 413, {"error": "file too large"}
    cfg = model_config()
    if cfg.problem():
        return 500, {"error": f"server model not configured: {cfg.problem()}"}
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state"
        if isinstance(body.get("session"), dict) and body["session"].get("runs") is not None:
            save(body["session"], state)
        name = Path(str(body.get("filename") or "message.txt")).name[:80]
        result = run(from_text(text, name), LLMClient(cfg, fallback=fallback_config()), state)
    sess = result["session"]
    return 200, {"ok": result["ok"], "error": result["error"], "run": result["run"], "session": sess,
                 "totals": token_totals(sess["calls"]), "model": cfg.model,
                 "submission": submission_text(sess)}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        cfg = model_config()
        self._send(200, {"configured": not cfg.problem(), "model": cfg.model, "problem": cfg.problem()})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except (json.JSONDecodeError, ValueError):
            return self._send(400, {"error": "send JSON"})
        code, obj = process(body)
        return self._send(code, obj)
