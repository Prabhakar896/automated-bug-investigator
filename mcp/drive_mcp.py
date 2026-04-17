"""
Google Drive MCP tool client.

Tools: search_files, upload_file
Used by: Triage Agent (runbook search), Fix Planner (report upload)
"""

from mcp.base_mcp import BaseMCPClient


class DriveMCPClient(BaseMCPClient):
    """MCP client for Google Drive operations."""

    def __init__(self, demo_mode: bool = True):
        super().__init__(server_name="google_drive", demo_mode=demo_mode)

    def search_files(self, query: str, max_results: int = 5) -> dict:
        """Search for files in Google Drive."""
        return self.call_tool("search_files", {
            "query": query, "max_results": max_results,
        })

    def upload_file(self, file_name: str, content: str, folder_id: str = "") -> dict:
        """Upload a file to Google Drive."""
        return self.call_tool("upload_file", {
            "file_name": file_name,
            "content_length": len(content),
            "folder_id": folder_id or "shared_engineering_reports",
        })

    def _get_demo_response(self, tool_name: str, params: dict) -> dict:
        responses = {
            "search_files": {
                "total_results": 2,
                "files": [
                    {
                        "id": "doc_runbook_001",
                        "name": "Payment Service — Incident Runbook",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2023-11-20T10:00:00Z",
                        "webViewLink": "https://docs.google.com/document/d/runbook_001",
                    },
                    {
                        "id": "doc_arch_002",
                        "name": "Payment Service Architecture",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2023-09-15T14:00:00Z",
                        "webViewLink": "https://docs.google.com/document/d/arch_002",
                    },
                ],
            },
            "upload_file": {
                "id": "file_report_uploaded_001",
                "name": params.get("file_name", "report.json"),
                "webViewLink": "https://drive.google.com/file/d/report_001/view",
                "status": "uploaded",
            },
        }
        return responses.get(tool_name, {"status": "ok"})
