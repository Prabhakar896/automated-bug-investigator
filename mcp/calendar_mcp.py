"""
Google Calendar MCP tool client.

Tools: list_events, create_event
Used by: Communication Agent (post-mortem scheduling)
"""

from mcp.base_mcp import BaseMCPClient


class CalendarMCPClient(BaseMCPClient):
    """MCP client for Google Calendar operations."""

    def __init__(self, demo_mode: bool = True):
        super().__init__(server_name="google_calendar", demo_mode=demo_mode)

    def list_events(self, time_min: str = "", time_max: str = "", max_results: int = 5) -> dict:
        """List upcoming calendar events."""
        return self.call_tool("list_events", {
            "time_min": time_min, "time_max": time_max, "max_results": max_results,
        })

    def create_event(
        self, summary: str, description: str, start_time: str,
        end_time: str, attendees: list = None,
    ) -> dict:
        """Create a calendar event (e.g., post-mortem meeting)."""
        return self.call_tool("create_event", {
            "summary": summary,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees or [],
        })

    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        responses = {
            "list_events": {
                "events": [
                    {
                        "id": "evt_release_001",
                        "summary": "v2.5.0 Release Window",
                        "start": "2024-01-22T14:00:00Z",
                        "end": "2024-01-22T16:00:00Z",
                        "status": "confirmed",
                    },
                    {
                        "id": "evt_standup_002",
                        "summary": "Daily Engineering Standup",
                        "start": "2024-01-16T09:00:00Z",
                        "end": "2024-01-16T09:15:00Z",
                        "status": "confirmed",
                    },
                ],
            },
            "create_event": {
                "id": "evt_postmortem_003",
                "summary": params.get("summary", "Post-mortem"),
                "status": "confirmed",
                "htmlLink": "https://calendar.google.com/event?id=evt_postmortem_003",
            },
        }
        return responses.get(tool_name, {"status": "ok"})
