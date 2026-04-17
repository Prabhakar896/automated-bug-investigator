"""
Base agent — abstract class that all pipeline agents inherit from.

Provides:
  - Timeout enforcement via asyncio
  - Retry logic (configurable max retries)
  - Structured trace logging for every execution step
  - Error handling with graceful degradation
"""

import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, Type, TypeVar

from pydantic import BaseModel

from config import Config
from models.investigation_report import AgentTraceEntry
from utils.logger import AgentTimer, get_logger

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents."""

    name: str = "unnamed_agent"
    description: str = ""

    def __init__(self):
        self.logger = get_logger(self.name)
        self.timeout = Config.AGENT_TIMEOUT_SECONDS
        self.max_retries = Config.AGENT_MAX_RETRIES
        self._trace_entries: list[AgentTraceEntry] = []
        self._tool_calls: list[str] = []

    @abstractmethod
    def execute(self, input_data: Any, context: dict) -> Any:
        """
        Execute the agent's main logic.

        Args:
            input_data: Typed input from upstream agent
            context: Shared pipeline context with all prior outputs

        Returns:
            Typed output for downstream agents
        """
        ...

    def run(self, input_data: Any, context: dict) -> Any:
        """
        Run the agent with timeout enforcement, retry logic, and tracing.
        
        This is the public interface called by the orchestrator.
        """
        self._tool_calls = []
        start_time = time.time()
        last_error = None

        for attempt in range(1, self.max_retries + 2):  # +2 because range is exclusive and we want 1 + retries
            try:
                self.logger.info(
                    f"> Starting {self.name} (attempt {attempt})",
                    extra={"agent_name": self.name, "action": "start"},
                )

                # Execute with timeout
                result = self._run_with_timeout(input_data, context)

                duration_ms = int((time.time() - start_time) * 1000)
                
                # Log success trace entry
                trace = AgentTraceEntry(
                    agent_name=self.name,
                    step="execute",
                    input_summary=self._summarize(input_data),
                    output_summary=self._summarize(result),
                    duration_ms=duration_ms,
                    tool_calls=self._tool_calls.copy(),
                    status="success",
                )
                self._trace_entries.append(trace)

                self.logger.info(
                    f"[OK] {self.name} completed in {duration_ms}ms",
                    extra={
                        "agent_name": self.name,
                        "action": "complete",
                        "duration_ms": duration_ms,
                        "status": "success",
                    },
                )
                return result

            except TimeoutError:
                last_error = f"Agent timed out after {self.timeout}s"
                self.logger.warning(
                    f"[TIMEOUT] {self.name} timed out (attempt {attempt})",
                    extra={"agent_name": self.name, "action": "timeout"},
                )
            except Exception as e:
                last_error = str(e)
                self.logger.error(
                    f"[FAIL] {self.name} failed (attempt {attempt}): {e}",
                    extra={"agent_name": self.name, "action": "error"},
                )
                self.logger.debug(traceback.format_exc())

            if attempt <= self.max_retries:
                self.logger.info(f"[RETRY] Retrying {self.name}...")

        # All attempts exhausted — log failure and return fallback
        duration_ms = int((time.time() - start_time) * 1000)
        trace = AgentTraceEntry(
            agent_name=self.name,
            step="execute",
            input_summary=self._summarize(input_data),
            output_summary=f"FAILED: {last_error}",
            duration_ms=duration_ms,
            tool_calls=self._tool_calls.copy(),
            status="failed",
        )
        self._trace_entries.append(trace)

        self.logger.error(
            f"[FAIL] {self.name} failed after all retries: {last_error}",
            extra={
                "agent_name": self.name,
                "action": "failed",
                "duration_ms": duration_ms,
                "status": "failed",
            },
        )

        # Return fallback output so pipeline can continue
        return self.get_fallback_output(last_error)

    def _run_with_timeout(self, input_data: Any, context: dict) -> Any:
        """Execute with timeout enforcement."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.execute, input_data, context)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"{self.name} exceeded timeout of {self.timeout}s"
                )

    def get_fallback_output(self, error: str) -> Any:
        """
        Return a safe fallback output when the agent fails.
        Override in subclasses for agent-specific fallbacks.
        """
        return None

    def log_tool_call(self, tool_name: str, details: str = ""):
        """Record an MCP or internal tool call for the trace."""
        call_str = f"{tool_name}"
        if details:
            call_str += f": {details}"
        self._tool_calls.append(call_str)
        self.logger.debug(
            f"  [TOOL] {call_str}",
            extra={"agent_name": self.name, "action": "tool_call"},
        )

    @property
    def trace_entries(self) -> list[AgentTraceEntry]:
        """Return all trace entries logged by this agent."""
        return self._trace_entries

    @staticmethod
    def _summarize(data: Any, max_len: int = 200) -> str:
        """Create a concise string summary of input/output data."""
        if data is None:
            return "None"
        if isinstance(data, BaseModel):
            text = data.model_dump_json()
        elif isinstance(data, dict):
            import json
            text = json.dumps(data, default=str)
        elif isinstance(data, str):
            text = data
        else:
            text = str(data)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text
