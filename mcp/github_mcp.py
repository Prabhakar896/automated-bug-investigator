"""
GitHub MCP tool client.

Tools: search_code, get_file_contents, list_commits, get_commit,
       create_issue, create_pull_request

Used by: Log Analyst (deploy correlation), Repo Navigator (code search),
         Fix Planner (issue creation)
"""

from mcp.base_mcp import BaseMCPClient


class GitHubMCPClient(BaseMCPClient):
    """MCP client for GitHub repository operations."""

    def __init__(self, demo_mode: bool = True, repo: str = "antigravity/payment-service"):
        super().__init__(server_name="github", demo_mode=demo_mode)
        self.repo = repo

    def search_code(self, query: str) -> dict:
        """Search for code patterns in the repository."""
        return self.call_tool("search_code", {"query": query, "repo": self.repo})

    def get_file_contents(self, path: str) -> dict:
        """Retrieve contents of a specific file."""
        return self.call_tool("get_file_contents", {"path": path, "repo": self.repo})

    def list_commits(self, since: str = "", until: str = "", limit: int = 10) -> dict:
        """List recent commits, optionally filtered by date range."""
        return self.call_tool("list_commits", {
            "repo": self.repo, "since": since, "until": until, "limit": limit
        })

    def get_commit(self, sha: str) -> dict:
        """Get details of a specific commit."""
        return self.call_tool("get_commit", {"repo": self.repo, "sha": sha})

    def create_issue(self, title: str, body: str, labels: list = None) -> dict:
        """Create a new issue in the repository."""
        return self.call_tool("create_issue", {
            "repo": self.repo, "title": title, "body": body,
            "labels": labels or ["bug", "auto-triage"],
        })

    def create_pull_request(self, title: str, body: str, branch: str) -> dict:
        """Create a draft pull request."""
        return self.call_tool("create_pull_request", {
            "repo": self.repo, "title": title, "body": body,
            "head": branch, "base": "main", "draft": True,
        })

    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        """Return simulated GitHub responses."""
        responses = {
            "search_code": {
                "total_count": 3,
                "items": [
                    {
                        "path": "src/services/payment_service.py",
                        "matched_lines": [
                            "discount_amount = round(gross * (discount.value / 100), 2)",
                            "total = round(gross - discount_amount, 2)",
                        ],
                        "score": 0.95,
                    },
                    {
                        "path": "src/app.py",
                        "matched_lines": [
                            "order = create_order_with_discount(",
                        ],
                        "score": 0.72,
                    },
                    {
                        "path": "src/utils.py",
                        "matched_lines": [
                            "def calculate_tax(subtotal, tax_rate=0.08):",
                        ],
                        "score": 0.45,
                    },
                ],
            },
            "get_file_contents": {
                "path": params.get("path", ""),
                "content": "# File content retrieved from GitHub",
                "encoding": "utf-8",
                "size": 2048,
            },
            "list_commits": {
                "commits": [
                    {
                        "sha": "a1b2c3d",
                        "message": "feat: add percentage discount support (v2.4.1)",
                        "author": "intern@antigravity.dev",
                        "date": "2024-01-15T14:30:00Z",
                        "files_changed": [
                            "src/services/payment_service.py",
                            "src/models.py",
                        ],
                    },
                    {
                        "sha": "e4f5g6h",
                        "message": "refactor: payment service for discount types (v2.4.0)",
                        "author": "intern@antigravity.dev",
                        "date": "2024-01-10T10:00:00Z",
                        "files_changed": [
                            "src/services/payment_service.py",
                        ],
                    },
                    {
                        "sha": "i7j8k9l",
                        "message": "chore: update dependencies",
                        "author": "devops@antigravity.dev",
                        "date": "2024-01-08T09:00:00Z",
                        "files_changed": ["requirements.txt"],
                    },
                ],
            },
            "get_commit": {
                "sha": params.get("sha", "a1b2c3d"),
                "message": "feat: add percentage discount support (v2.4.1)",
                "author": "intern@antigravity.dev",
                "date": "2024-01-15T14:30:00Z",
                "stats": {"additions": 45, "deletions": 12},
                "files": [
                    {"filename": "src/services/payment_service.py", "status": "modified"},
                ],
            },
            "create_issue": {
                "number": 142,
                "url": "https://github.com/antigravity/payment-service/issues/142",
                "title": params.get("title", "Bug report"),
                "state": "open",
            },
            "create_pull_request": {
                "number": 87,
                "url": "https://github.com/antigravity/payment-service/pull/87",
                "title": params.get("title", "Fix"),
                "state": "draft",
            },
        }
        return responses.get(tool_name, {"status": "ok"})
