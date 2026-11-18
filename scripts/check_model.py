"""Run this first at the venue:  python scripts/check_model.py
Checks the key, lists models the key can use, and makes ONE tiny test call showing the token
counts the provider reports. (Not part of the judged pipeline; it does not touch the session.)
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from planforge.config import fallback_config, model_config  # noqa: E402


def check(cfg, label):
    print(f"== {label}: provider={cfg.provider} model={cfg.model} url={cfg.base_url}")
    if cfg.problem():
        print("   not configured:", cfg.problem())
        return
    hdr = {"Content-Type": "application/json", **({"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {})}
    try:
        data = json.loads(urllib.request.urlopen(urllib.request.Request(cfg.base_url + "/models", headers=hdr), timeout=20).read())
        ids = sorted(m.get("id", "") for m in data.get("data", []))
        small = [i for i in ids if any(w in i.lower() for w in ("lite", "mini", "nano", "small", "8b", "flash", "gemma", "3b", "1b"))]
        print(f"   {len(ids)} models available; small-looking ones: {', '.join(small[:25]) or '-'}")
    except Exception as e:  # noqa: BLE001
        print("   could not list models:", str(e)[:200])
    body = {"model": cfg.model, "temperature": 0, "messages": [{"role": "user", "content": 'Reply with JSON {"ok": true}'}]}
    if cfg.json_mode:
        body["response_format"] = {"type": "json_object"}
    t = time.monotonic()
    try:
        req = urllib.request.Request(cfg.base_url + "/chat/completions", data=json.dumps(body).encode(), headers=hdr, method="POST")
        data = json.loads(urllib.request.urlopen(req, timeout=cfg.timeout).read())
        print(f"   OK in {time.monotonic() - t:.1f}s, model reported: {data.get('model')}")
        print(f"   reply: {data['choices'][0]['message']['content'][:80]!r}")
        print(f"   usage as reported: {data.get('usage')}")
    except urllib.error.HTTPError as e:
        print(f"   FAILED HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    except Exception as e:  # noqa: BLE001
        print("   FAILED:", str(e)[:300])


check(model_config(), "primary")
fb = fallback_config()
if fb:
    check(fb, "fallback")
