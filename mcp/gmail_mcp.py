"""
Gmail MCP tool client.

Tools: search_emails, send_email
Used by: Triage Agent (prior report search), Communication Agent (notifications)
"""

from mcp.base_mcp import BaseMCPClient


class GmailMCPClient(BaseMCPClient):
    """MCP client for Gmail operations."""

    def __init__(self, demo_mode: bool = True):
        super().__init__(server_name="gmail", demo_mode=demo_mode)

    def search_emails(self, query: str, max_results: int = 5) -> dict:
        """Search for emails matching a query."""
        return self.call_tool("search_emails", {
            "query": query, "max_results": max_results,
        })

    def send_email(self, to: str, subject: str, body: str) -> dict:
        """Send an email notification."""
        return self.call_tool("send_email", {
            "to": to, "subject": subject, "body": body,
        })

    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        responses = {
            "search_emails": {
                "total_results": 1,
                "emails": [
                    {
                        "id": "msg_abc123",
                        "subject": "Re: Payment errors after v2.4.1 deploy",
                        "from": "support@antigravity.dev",
                        "date": "2024-01-15T16:00:00Z",
                        "snippet": "We're seeing multiple customers reporting failed payments "
                                   "when using the PROMO100 code. The error mentions negative "
                                   "payment amounts. Escalating to engineering.",
                    },
                ],
            },
            "send_email": {
                "message_id": "msg_sent_xyz789",
                "status": "sent",
                "to": params.get("to", ""),
                "subject": params.get("subject", ""),
            },
        }
        return responses.get(tool_name, {"status": "ok"})
