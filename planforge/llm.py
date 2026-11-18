"""The ONLY place that talks to a model. Every attempt (success or error) becomes a CallRecord.

Uses the OpenAI-compatible /chat/completions API over urllib (stdlib), so the CLI needs no packages.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .config import ModelConfig
from .trace import CallRecord


class CallBudgetExceeded(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: ModelConfig, transport=None, fallback: ModelConfig = None):
        self.primary, self.fallback = cfg, fallback
        self.cfg = cfg
        self.transport = transport or self._http   # tests inject a scripted transport
        self.records: list = []
        self.next_number = 1
        self.run_id = 0
        self.max_calls = 5
        self.deadline = None

    # ------------------------------------------------------------------ transport
    def _http(self, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            self.cfg.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:600]
            raise RuntimeError(f"HTTP {e.code}: {body}") from None

    # ------------------------------------------------------------------ call
    def chat(self, tag: str, system: str, user: str, json_mode: bool = True) -> CallRecord:
        mine = [r for r in self.records if r.run_id == self.run_id]
        # after a failed call in this run, switch to the fallback model (if configured); traced under its own name
        self.cfg = self.fallback if (self.fallback and mine and mine[-1].status != "ok") else self.primary
        if len(mine) >= self.max_calls:
            raise CallBudgetExceeded(f"call limit of {self.max_calls} reached for this run")
        timeout = self.cfg.timeout
        if self.deadline is not None:
            timeout = min(timeout, max(1.0, self.deadline - time.monotonic()))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        payload = {"model": self.cfg.model, "messages": messages, "temperature": 0}
        if json_mode and self.cfg.json_mode:
            payload["response_format"] = {"type": "json_object"}

        rec = CallRecord(number=self.next_number, run_id=self.run_id, tag=tag, model=self.cfg.model,
                         request=messages, response="", status="error",
                         timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.next_number += 1
        t0 = time.monotonic()
        try:
            data = self.transport(payload, timeout)
            choice = (data.get("choices") or [{}])[0]
            rec.response = (choice.get("message") or {}).get("content") or ""
            rec.model = data.get("model") or self.cfg.model
            usage = data.get("usage") or {}
            rec.usage_raw = usage
            rec.input_tokens = usage.get("prompt_tokens")
            rec.output_tokens = usage.get("completion_tokens")
            rec.total_tokens = usage.get("total_tokens")
            rec.status = "ok"
        except Exception as e:  # noqa: BLE001 - every failure is recorded honestly
            rec.error = str(e)[:600]
        rec.seconds = round(time.monotonic() - t0, 2)
        self.records.append(rec)
        return rec
