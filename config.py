"""
Configuration management — loads settings from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class Config:
    """Central configuration loaded from environment variables."""

    # ─── LLM Settings ─────────────────────────────────────────────
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    # ─── Agent Settings ───────────────────────────────────────────
    AGENT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "60"))
    AGENT_MAX_RETRIES: int = int(os.getenv("AGENT_MAX_RETRIES", "1"))

    # ─── MCP Settings ─────────────────────────────────────────────
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "antigravity/payment-service")
    GOOGLE_MCP_TOKEN: str = os.getenv("GOOGLE_MCP_TOKEN", "")
    MCP_DEMO_MODE: bool = os.getenv("MCP_DEMO_MODE", "true").lower() == "true"

    # ─── Output Settings ──────────────────────────────────────────
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./output")
    REPRO_DIR: str = os.getenv("REPRO_DIR", "./repro")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ─── Project Paths ────────────────────────────────────────────
    PROJECT_ROOT: Path = Path(__file__).parent.resolve()
    SRC_DIR: Path = PROJECT_ROOT / "src"

    @classmethod
    def ensure_directories(cls):
        """Create output directories if they don't exist."""
        for dir_path in [cls.OUTPUT_DIR, cls.REPRO_DIR, cls.LOG_DIR]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_llm_available(cls) -> bool:
        """Check if LLM API key is configured."""
        return bool(cls.GOOGLE_API_KEY)

    @classmethod
    def summary(cls) -> dict:
        """Return a summary of the current configuration (safe to log)."""
        return {
            "llm_model": cls.LLM_MODEL,
            "llm_available": cls.is_llm_available(),
            "agent_timeout_seconds": cls.AGENT_TIMEOUT_SECONDS,
            "mcp_demo_mode": cls.MCP_DEMO_MODE,
            "output_dir": cls.OUTPUT_DIR,
            "log_level": cls.LOG_LEVEL,
        }
