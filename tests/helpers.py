"""Test-only scripted transport: returns a fixture as if a model had answered. Never used by main.py."""
import json
from pathlib import Path

from planforge.config import ModelConfig
from planforge.llm import LLMClient

FIX = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).parent.parent / "samples"
TEST_CFG = ModelConfig(provider="test", base_url="", api_key="", model="scripted-test-model", timeout=5, json_mode=True)


def scripted(*fixture_names, usage=(100, 50)):
    queue = [json.dumps(json.loads((FIX / n).read_text(encoding="utf-8"))) if n.endswith(".json") else n
             for n in fixture_names]

    def transport(payload, timeout):
        content = queue.pop(0)
        if content == "ERROR":
            raise RuntimeError("HTTP 503: test outage")
        return {"model": "scripted-test-model", "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}}
    return LLMClient(TEST_CFG, transport=transport)
