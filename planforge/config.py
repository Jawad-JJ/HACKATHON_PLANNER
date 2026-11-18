"""Model configuration from .env (no third-party packages).

Any OpenAI-compatible chat endpoint works: Groq, Gemini (OpenAI mode), OpenAI, Ollama (local).
"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "ollama": ("http://localhost:11434/v1", ""),
}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


@dataclass
class ModelConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    json_mode: bool

    def problem(self) -> str:
        if not self.model:
            return "LLM_MODEL is not set in .env"
        if self.provider != "ollama" and not self.api_key:
            return f"No API key for provider '{self.provider}' (set it in .env)"
        return ""


def model_config(prefix: str = "LLM_") -> ModelConfig:
    """prefix LLM_ = primary model; LLM_FALLBACK_ = optional second model used only if the first call fails."""
    load_dotenv()
    provider = os.getenv(prefix + "PROVIDER", "groq" if prefix == "LLM_" else "").strip().lower()
    base, key_var = PRESETS.get(provider, ("", ""))
    base_url = os.getenv(prefix + "BASE_URL", "").strip() or base
    api_key = os.getenv(prefix + "API_KEY", "").strip() or (os.getenv(key_var, "").strip() if key_var else "")
    return ModelConfig(
        provider=provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=os.getenv(prefix + "MODEL", "").strip(),
        timeout=float(os.getenv("LLM_TIMEOUT", "40")),
        json_mode=os.getenv("LLM_JSON_MODE", "1").strip() != "0",
    )


def fallback_config():
    cfg = model_config("LLM_FALLBACK_")
    return None if (not cfg.provider or cfg.problem()) else cfg
