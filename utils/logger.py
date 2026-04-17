"""
Structured logging setup for the agent pipeline.

Provides dual logging:
  - Console: human-readable, colored output
  - File: JSON-structured entries in logs/agent_trace.log
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra fields if present
        for key in ["agent_name", "action", "input_summary", "output_summary",
                     "duration_ms", "tool_calls", "status", "mcp_server",
                     "tool_name", "parameters", "result"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable colored console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        # Add agent context if available
        prefix = ""
        if hasattr(record, "agent_name"):
            prefix = f" [{record.agent_name}]"
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg = record.getMessage()
        
        return (
            f"{color}{timestamp} "
            f"{self.BOLD}{record.levelname:<8}{self.RESET}"
            f"{color}{prefix} {msg}{self.RESET}"
        )


def setup_logging(log_level: str = "INFO", log_dir: str = "./logs") -> logging.Logger:
    """
    Configure dual logging: console + JSON file.
    
    Returns the root pipeline logger.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    trace_file = log_path / "agent_trace.log"

    # Clear previous trace log
    if trace_file.exists():
        trace_file.unlink()

    root_logger = logging.getLogger("pipeline")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.handlers.clear()

    # Console handler — use error-tolerant encoding for Windows
    import io
    console_stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    ) if hasattr(sys.stdout, "buffer") else sys.stdout
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # File handler (JSON)
    file_handler = logging.FileHandler(str(trace_file), mode="w", encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific agent or module."""
    return logging.getLogger(f"pipeline.{name}")


class AgentTimer:
    """Context manager for timing agent execution."""
    
    def __init__(self, agent_name: str, logger: Optional[logging.Logger] = None):
        self.agent_name = agent_name
        self.logger = logger or get_logger(agent_name)
        self.start_time = 0.0
        self.duration_ms = 0

    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(
            f"Starting execution",
            extra={"agent_name": self.agent_name, "action": "start"}
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = int((time.time() - self.start_time) * 1000)
        status = "success" if exc_type is None else "failed"
        self.logger.info(
            f"Completed in {self.duration_ms}ms (status: {status})",
            extra={
                "agent_name": self.agent_name,
                "action": "complete",
                "duration_ms": self.duration_ms,
                "status": status,
            }
        )
        return False  # Don't suppress exceptions
