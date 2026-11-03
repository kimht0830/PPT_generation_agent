"""Model selection and shared settings."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT_DIR.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
OUTPUT_DIR = ROOT_DIR / "outputs"
# <conf><year>_<key>/paper.pdf + slides.pdf pairs; slides.pdf is the human reference.
EXAMPLES_DIR = PROJECT_DIR / "examples"

load_dotenv(ROOT_DIR / ".env")


DEFAULT_MODEL = "anthropic/claude-haiku-5.5"


def model_id(agent: str) -> str:
    """Model id for an agent, read from <AGENT>_MODEL in .env (e.g. WRITER_MODEL).

    Falls back to DEFAULT_MODEL when the variable is not set. The value is an
    OpenRouter model id; the "openrouter/" prefix is optional.
    """
    value = os.getenv(f"{agent.upper()}_MODEL", "").strip() or DEFAULT_MODEL
    return value if value.startswith("openrouter/") else f"openrouter/{value}"


def get_model(agent: str) -> LiteLlm:
    return LiteLlm(model=model_id(agent))


def load_prompt(name: str) -> str:
    """Read prompts/<name>.md."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
