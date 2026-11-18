"""Local web dashboard + API, using the SAME pipeline as `python main.py <file>`.

    python serve.py            -> http://127.0.0.1:8000
    HOST=0.0.0.0 python serve.py   (open from a phone on the same Wi-Fi)

GET  /api/state            current session (plan, messages, decisions, full trace, totals)
POST /api/message {text}   saves the text to state/inbox/*.txt and runs it through pipeline.run
GET  /api/export/<file>    files from outputs/ (submission.txt, full_trace.txt, ...)
"""
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from planforge.config import ROOT, fallback_config, model_config
from planforge.ingest import read_input
from planforge.llm import LLMClient
from planforge.pipeline import run
from planforge.render import export
from planforge.session import OUT_DIR, STATE_DIR, load
from planforge.trace import token_totals

WEB = ROOT / "web"
EXPORTS = {"submission.txt", "latest_plan.txt", "latest_plan.json", "full_trace.txt", "full_trace.json",
           "rejections.json", "updates.json", "session.json"}


def state_payload():
    sess = load() or {}
    return {"mode": "live", "model": model_config().model, "session": sess,
            "totals": token_totals(sess.get("calls", []))}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/state"):
            return self._json(state_payload())
        if self.path.startswith("/api/export/"):
            name = self.path.rsplit("/", 1)[-1]
            f = OUT_DIR / name
            if name not in EXPORTS or not f.exists():
                return self._json({"error": "not found - run a pack first"}, 404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8" if name.endswith(".txt") else "application/json")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/message"):
            return self._json({"error": "unknown endpoint"}, 404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "send JSON {\"text\": ...}"}, 400)
        text = str(body.get("text", ""))
        if not text.strip():
            return self._json({"error": "empty message"}, 400)
        cfg = model_config()
        if cfg.problem():
            return self._json({"error": f"model not configured: {cfg.problem()}"}, 400)
        inbox = STATE_DIR / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path.write_text(text, encoding="utf-8")            # same as giving main.py a file
        result = run(read_input(path), LLMClient(cfg, fallback=fallback_config()))
        export(result["session"])
        payload = state_payload()
        payload.update(ok=result["ok"], error=result["error"], run=result["run"])
        return self._json(payload)


if __name__ == "__main__":
    host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))
    print(f"PlanForge dashboard on http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
