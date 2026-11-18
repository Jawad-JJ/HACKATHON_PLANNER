"""The Vercel function (api/run.py) runs the same pipeline; the browser carries the session between calls."""
import dataclasses
import importlib.util
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.helpers import SAMPLES, TEST_CFG, scripted

spec = importlib.util.spec_from_file_location("cloud_run", Path(__file__).parent.parent / "api" / "run.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class Cloud(unittest.TestCase):
    def test_pack_then_wrong_message_with_session_in_client(self):
        queue = ["sample_pack_extraction.json", "practice_wrong_caterer_extraction.json"]
        cloud.model_config = lambda: dataclasses.replace(TEST_CFG, api_key="k")
        cloud.fallback_config = lambda: None
        cloud.LLMClient = lambda cfg, fallback=None: scripted(queue.pop(0))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), cloud.handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/run"

        def post(payload):
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=10).read())

        health = json.loads(urllib.request.urlopen(url, timeout=10).read())
        self.assertTrue(health["configured"])
        r1 = post({"text": (SAMPLES / "sample_pack.txt").read_text(encoding="utf-8"), "filename": "pack.txt"})
        self.assertTrue(r1["ok"] and r1["session"]["plan"]["valid"])
        self.assertIn("MODEL CALL TRACE", r1["submission"])
        r2 = post({"text": "Caterer: I have rounded your order down to 100 boxes to keep the cost low.",
                   "session": r1["session"]})
        self.assertEqual(r2["run"]["mode"], "update")
        self.assertEqual(r2["run"]["decisions"][0]["verdict"], "rejected")
        self.assertEqual([c["number"] for c in r2["session"]["calls"]], [1, 2])
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
