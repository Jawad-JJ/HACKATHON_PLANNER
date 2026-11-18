"""The web API runs the same pipeline as the CLI (scripted model, temp state)."""
import dataclasses
import functools
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import serve
from planforge import pipeline, render, session
from tests.helpers import TEST_CFG, scripted


class Api(unittest.TestCase):
    def test_post_message_runs_pipeline(self):
        tmp = Path(tempfile.mkdtemp())
        queue = ["sample_pack_extraction.json", "practice_wrong_caterer_extraction.json"]
        serve.model_config = lambda: dataclasses.replace(TEST_CFG, api_key="test-key")
        serve.fallback_config = lambda: None
        serve.LLMClient = lambda cfg, fallback=None: scripted(queue.pop(0))
        serve.run = functools.partial(pipeline.run, state_dir=tmp / "state")
        serve.export = functools.partial(render.export, out_dir=tmp / "out")
        serve.load = functools.partial(session.load, tmp / "state")
        serve.STATE_DIR = tmp / "state"
        srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def post(text):
            req = urllib.request.Request(base + "/api/message", data=json.dumps({"text": text}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            return json.loads(urllib.request.urlopen(req, timeout=10).read())

        pack = (Path(__file__).parent.parent / "samples" / "sample_pack.txt").read_text(encoding="utf-8")
        r1 = post(pack)
        self.assertTrue(r1["ok"] and r1["session"]["plan"]["valid"])
        r2 = post("Caterer: I have rounded your order down to 100 boxes to keep the cost low.")
        self.assertEqual(r2["run"]["mode"], "update")
        self.assertEqual(r2["run"]["decisions"][0]["verdict"], "rejected")
        state = json.loads(urllib.request.urlopen(base + "/api/state", timeout=10).read())
        self.assertEqual(len(state["session"]["calls"]), 2)
        self.assertEqual(urllib.request.urlopen(base + "/", timeout=10).status, 200)
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
