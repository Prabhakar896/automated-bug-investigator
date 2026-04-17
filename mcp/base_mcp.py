"""
Base MCP (Model Context Protocol) client.

Provides the abstract interface and common functionality for all MCP tool
integrations. In demo mode, returns simulated responses while logging the
exact calls that would be made to real MCP servers.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from utils.logger import get_logger


class BaseMCPClient(ABC):
    """Abstract base class for MCP tool clients."""

    def __init__(self, server_name: str, demo_mode: bool = True):
        self.server_name = server_name
        self.demo_mode = demo_mode
        self.logger = get_logger(f"mcp.{server_name}")
        self._call_history: list = []

    @abstractmethod
    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        """Return a simulated response for demo mode."""
        ...

    def call_tool(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        retry: bool = True,
    ) -> dict:
        """
        Call an MCP tool with the given parameters.

        Args:
            tool_name: Name of the tool to invoke
            params: Parameters to pass to the tool
            retry: Whether to retry on failure (1 retry max)

        Returns:
            Tool response as a dict
        """
        params = params or {}
        call_record = {
            "mcp_server": self.server_name,
            "tool_name": tool_name,
            "parameters": params,
            "demo_mode": self.demo_mode,
        }

        self.logger.info(
            f"Calling {self.server_name}.{tool_name}",
            extra={
                "mcp_server": self.server_name,
                "tool_name": tool_name,
                "parameters": json.dumps(params, default=str),
                "action": "mcp_call",
            },
        )

        if self.demo_mode:
            result = self._get_demo_response(tool_name, params)
            call_record["result"] = result
            call_record["status"] = "success (demo)"
            self._call_history.append(call_record)
            self.logger.info(
                f"[DEMO] {self.server_name}.{tool_name} → simulated response",
                extra={
                    "mcp_server": self.server_name,
                    "tool_name": tool_name,
                    "result": json.dumps(result, default=str)[:200],
                },
            )
            return result

        # Real MCP call (placeholder for actual MCP protocol implementation)
        attempts = 2 if retry else 1
        last_error = None

        for attempt in range(attempts):
            try:
                result = self._execute_real_call(tool_name, params)
                call_record["result"] = result
                call_record["status"] = "success"
                self._call_history.append(call_record)
                return result
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"MCP call failed (attempt {attempt + 1}/{attempts}): {e}",
                    extra={"mcp_server": self.server_name, "tool_name": tool_name},
                )

        # All retries exhausted
        call_record["status"] = f"failed: {last_error}"
        self._call_history.append(call_record)
        self.logger.error(
            f"MCP call failed after {attempts} attempts: {last_error}",
            extra={"mcp_server": self.server_name, "tool_name": tool_name},
        )
        return {"error": str(last_error), "success": False}

    def _execute_real_call(self, tool_name: str, params: dict) -> dict:
        """
        Execute a real MCP call. Override in subclasses for actual implementations.
        
        In a production system, this would use the MCP protocol to communicate
        with the external server via stdio/SSE transport.
        """
        raise NotImplementedError(
            f"Real MCP calls not implemented for {self.server_name}. "
            f"Set MCP_DEMO_MODE=true to use simulated responses."
        )

    @property
    def call_history(self) -> list:
        """Return the history of all MCP tool calls."""
        return self._call_history

    def get_call_summary(self) -> list:
        """Return a concise summary of all calls made."""
        return [
            {
                "server": c["mcp_server"],
                "tool": c["tool_name"],
                "status": c.get("status", "unknown"),
            }
            for c in self._call_history
        ]
