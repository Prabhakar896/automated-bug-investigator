"""
Talent Search MCP tool client (Indeed/Dice creative integration).

Tools: search_candidates
Used by: Communication Agent — if the fix requires specialist skills the
current team lacks, queries talent platforms to draft a contractor spec.
"""

from mcp.base_mcp import BaseMCPClient


class TalentMCPClient(BaseMCPClient):
    """MCP client for talent/recruiting platform operations."""

    def __init__(self, demo_mode: bool = True):
        super().__init__(server_name="talent_search", demo_mode=demo_mode)

    def search_candidates(self, skills: list, experience_level: str = "senior") -> dict:
        """Search for candidates with specific skills."""
        return self.call_tool("search_candidates", {
            "skills": skills,
            "experience_level": experience_level,
            "platforms": ["indeed", "dice"],
        })

    def draft_contractor_spec(self, role: str, skills: list, duration: str) -> dict:
        """Draft a contractor requirement specification."""
        return self.call_tool("draft_contractor_spec", {
            "role": role,
            "required_skills": skills,
            "estimated_duration": duration,
        })

    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        responses = {
            "search_candidates": {
                "total_results": 15,
                "top_candidates": [
                    {
                        "title": "Senior Python Engineer — FinTech Specialist",
                        "experience": "7 years",
                        "skills": params.get("skills", []),
                        "availability": "immediate",
                        "platform": "indeed",
                    },
                ],
                "market_insight": "Payment processing specialists are in high demand. "
                                  "Average contract rate: $150-200/hr.",
            },
            "draft_contractor_spec": {
                "spec": {
                    "role": params.get("role", "Contract Engineer"),
                    "skills": params.get("required_skills", []),
                    "duration": params.get("estimated_duration", "2 weeks"),
                    "description": "Seeking a contract engineer to assist with "
                                   "payment processing bug remediation and testing.",
                },
                "status": "drafted",
            },
        }
        return responses.get(tool_name, {"status": "ok"})
