"""
Communication Agent (Bonus) — executes MCP actions for team coordination.

MCP integrations:
  - Calendar: schedule post-mortem if severity HIGH/CRITICAL
  - Gmail: send final investigation summary email
  - Talent: draft contractor spec if specialist skills needed
"""

from datetime import datetime, timedelta

from config import Config
from models.agent_outputs import (
    CommunicationOutput,
    MCPAction,
)
from agents.base_agent import BaseAgent
from mcp.calendar_mcp import CalendarMCPClient
from mcp.gmail_mcp import GmailMCPClient
from mcp.talent_mcp import TalentMCPClient


class CommunicationAgent(BaseAgent):
    name = "communication_agent"
    description = "Execute MCP actions for team coordination, notifications, and follow-ups"

    def __init__(self):
        super().__init__()
        self.calendar = CalendarMCPClient(demo_mode=Config.MCP_DEMO_MODE)
        self.gmail = GmailMCPClient(demo_mode=Config.MCP_DEMO_MODE)
        self.talent = TalentMCPClient(demo_mode=Config.MCP_DEMO_MODE)

    def execute(self, input_data: dict, context: dict) -> CommunicationOutput:
        """
        Perform team coordination actions based on investigation results.
        """
        triage = context.get("triage_output")
        fix_plan = context.get("fix_plan_output")
        review = context.get("review_output")
        
        actions = []
        calendar_event_id = ""
        email_sent_to = ""
        github_issue_url = fix_plan.github_issue_url if fix_plan else ""
        drive_report_url = fix_plan.drive_report_url if fix_plan else ""
        talent_search_performed = False

        severity = triage.severity if triage else "HIGH"

        # Step 1: Check upcoming release windows
        self.log_tool_call("calendar.list_events", "checking release windows")
        events_result = self.calendar.list_events(
            time_min=datetime.utcnow().isoformat() + "Z",
            time_max=(datetime.utcnow() + timedelta(days=14)).isoformat() + "Z",
        )
        actions.append(MCPAction(
            mcp_server="google_calendar",
            tool_name="list_events",
            parameters={"time_range": "next 14 days"},
            result=f"Found {len(events_result.get('events', []))} upcoming events",
            success=True,
        ))

        # Step 2: Schedule post-mortem if severity is HIGH or CRITICAL
        if severity in ("HIGH", "CRITICAL"):
            self.log_tool_call("calendar.create_event", "scheduling post-mortem")
            postmortem_time = datetime.utcnow() + timedelta(days=1, hours=2)
            event_result = self.calendar.create_event(
                summary=f"[Post-Mortem] {triage.bug_title if triage else 'Payment Bug'}",
                description=(
                    f"Post-mortem for bug: {triage.bug_title if triage else 'Negative payment amount'}\n\n"
                    f"Root Cause: {fix_plan.root_cause_hypothesis[:200] if fix_plan else 'TBD'}\n\n"
                    f"Confidence: {fix_plan.confidence_pct if fix_plan else 0}%\n"
                    f"GitHub Issue: {github_issue_url}\n"
                    f"Investigation Report: {drive_report_url}"
                ),
                start_time=postmortem_time.isoformat() + "Z",
                end_time=(postmortem_time + timedelta(hours=1)).isoformat() + "Z",
                attendees=[
                    "eng-lead@antigravity.dev",
                    "payments-team@antigravity.dev",
                    "oncall@antigravity.dev",
                ],
            )
            calendar_event_id = event_result.get("id", "")
            actions.append(MCPAction(
                mcp_server="google_calendar",
                tool_name="create_event",
                parameters={"summary": "Post-mortem meeting"},
                result=f"Event created: {calendar_event_id}",
                success=True,
            ))

        # Step 3: Send email notification
        team_summary = self._build_team_summary(triage, fix_plan, review)
        
        self.log_tool_call("gmail.send_email", "notifying engineering lead")
        email_result = self.gmail.send_email(
            to="eng-lead@antigravity.dev",
            subject=f"[{severity}] Automated Bug Investigation: {triage.bug_title if triage else 'Payment Bug'}",
            body=team_summary,
        )
        email_sent_to = "eng-lead@antigravity.dev"
        actions.append(MCPAction(
            mcp_server="gmail",
            tool_name="send_email",
            parameters={"to": email_sent_to},
            result=f"Email sent: {email_result.get('message_id', '')}",
            success=True,
        ))

        # Step 4: Creative MCP chaining — if fix requires specialist skills
        if fix_plan and fix_plan.confidence_pct < 50:
            self.log_tool_call("talent.search_candidates", "searching for specialists")
            talent_result = self.talent.search_candidates(
                skills=["payment processing", "Python", "financial calculations"],
                experience_level="senior",
            )
            talent_search_performed = True
            actions.append(MCPAction(
                mcp_server="talent_search",
                tool_name="search_candidates",
                parameters={"skills": ["payment processing", "Python"]},
                result=f"Found {talent_result.get('total_results', 0)} candidates",
                success=True,
            ))

            self.log_tool_call("talent.draft_contractor_spec", "drafting contractor spec")
            self.talent.draft_contractor_spec(
                role="Payment Processing Specialist (Contract)",
                skills=["Python", "payment systems", "financial calculations", "pytest"],
                duration="2-4 weeks",
            )
            actions.append(MCPAction(
                mcp_server="talent_search",
                tool_name="draft_contractor_spec",
                parameters={"role": "Payment Processing Specialist"},
                result="Contractor spec drafted",
                success=True,
            ))

        return CommunicationOutput(
            actions_taken=actions,
            github_issue_url=github_issue_url,
            drive_report_url=drive_report_url,
            calendar_event_id=calendar_event_id,
            email_sent_to=email_sent_to,
            team_summary=team_summary,
            talent_search_performed=talent_search_performed,
        )

    def _build_team_summary(self, triage, fix_plan, review) -> str:
        """Build a human-readable summary for team handoff."""
        severity = triage.severity if triage else "HIGH"
        title = triage.bug_title if triage else "Payment Bug"
        summary = triage.bug_summary if triage else "See investigation report"
        
        confidence = fix_plan.confidence_pct if fix_plan else 0
        root_cause = fix_plan.root_cause_hypothesis[:300] if fix_plan else "TBD"
        
        review_status = review.approval_status if review else "pending"
        open_qs = review.open_questions if review else []

        return f"""🔍 Automated Bug Investigation Report
{'=' * 50}

📋 Bug: {title}
⚠️  Severity: {severity}
📊 Confidence: {confidence}%
✅ Review Status: {review_status}

📝 Summary:
{summary}

🔬 Root Cause:
{root_cause}

📂 Patch Plan:
{fix_plan.patch.approach if fix_plan else 'TBD'}

Files to modify:
{chr(10).join(f'  • {f}' for f in (fix_plan.patch.files_impacted if fix_plan else []))}

❓ Open Questions:
{chr(10).join(f'  • {q}' for q in open_qs[:5])}

🔗 Links:
  • GitHub Issue: {fix_plan.github_issue_url if fix_plan else 'N/A'}
  • Drive Report: {fix_plan.drive_report_url if fix_plan else 'N/A'}

—
Generated by Antigravity Bug Investigation Pipeline
"""

    def get_fallback_output(self, error: str) -> CommunicationOutput:
        return CommunicationOutput(
            team_summary=f"Communication agent failed: {error}",
        )
