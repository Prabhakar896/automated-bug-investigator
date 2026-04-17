"""
Triage Agent — reads bug report, extracts structured fields, generates hypotheses.

MCP integrations:
  - Gmail: search for prior reports of the same issue
  - Drive: search for relevant runbooks and known-issues docs
"""

from config import Config
from models.agent_outputs import (
    Hypothesis,
    HypothesisCategory,
    TriageOutput,
)
from models.bug_report import BugReport
from agents.base_agent import BaseAgent
from mcp.gmail_mcp import GmailMCPClient
from mcp.drive_mcp import DriveMCPClient
from utils.llm_client import get_llm_client


class TriageAgent(BaseAgent):
    name = "triage_agent"
    description = "Parse bug report, extract structured data, generate ranked hypotheses"

    def __init__(self):
        super().__init__()
        self.gmail = GmailMCPClient(demo_mode=Config.MCP_DEMO_MODE)
        self.drive = DriveMCPClient(demo_mode=Config.MCP_DEMO_MODE)

    def execute(self, input_data: BugReport, context: dict) -> TriageOutput:
        """
        1. Search Gmail for prior reports
        2. Search Drive for runbooks
        3. Use LLM to generate ranked hypotheses
        """
        # Step 1: Search Gmail for prior reports of this issue
        self.log_tool_call("gmail.search_emails", f"query='{input_data.title}'")
        email_results = self.gmail.search_emails(
            query=f"payment error negative amount {input_data.title}",
            max_results=5,
        )
        prior_reports = []
        for email in email_results.get("emails", []):
            prior_reports.append(
                f"[{email.get('date', '')}] {email.get('subject', '')} — {email.get('snippet', '')[:100]}"
            )

        # Step 2: Search Drive for runbooks
        self.log_tool_call("drive.search_files", "query='payment service runbook'")
        drive_results = self.drive.search_files(
            query="payment service incident runbook",
            max_results=5,
        )
        runbooks = []
        for doc in drive_results.get("files", []):
            runbooks.append(f"{doc.get('name', '')} — {doc.get('webViewLink', '')}")

        # Step 3: Generate hypotheses using LLM
        llm = get_llm_client()
        prompt = self._build_prompt(input_data, prior_reports, runbooks)

        if llm.is_available:
            self.log_tool_call("llm.generate", "generating hypotheses")
            response = llm.generate(
                prompt=prompt,
                system_instruction=(
                    "You are a senior bug triage engineer. Analyze the bug report "
                    "and produce a ranked list of root-cause hypotheses. Be specific "
                    "about which code modules and functions are likely involved."
                ),
                response_schema=TriageOutput,
            )
            try:
                output = TriageOutput(**response)
            except Exception:
                output = self._build_deterministic_output(input_data, prior_reports, runbooks)
        else:
            output = self._build_deterministic_output(input_data, prior_reports, runbooks)

        return output

    def _build_prompt(self, bug: BugReport, prior_reports: list, runbooks: list) -> str:
        return f"""Analyze this bug report and produce a structured triage output.

## Bug Report
- Title: {bug.title}
- Severity: {bug.severity.value}
- Description: {bug.description}
- Expected Behavior: {bug.expected_behavior}
- Actual Behavior: {bug.actual_behavior}
- Environment: {bug.environment}
- Reproduction Steps: {bug.repro_steps}

## Prior Reports Found (via Gmail)
{chr(10).join(prior_reports) if prior_reports else "None found"}

## Runbooks Found (via Drive)
{chr(10).join(runbooks) if runbooks else "None found"}

Generate:
1. A concise bug summary
2. List of observable symptoms
3. Ranked hypotheses (most likely first) with categories and evidence
4. List of affected components
"""

    def _build_deterministic_output(
        self, bug: BugReport, prior_reports: list, runbooks: list
    ) -> TriageOutput:
        """Deep analysis of the actual bug report using pattern database."""
        import re
        from utils.code_analyzer import classify_bug, extract_file_references, extract_error_types

        title = bug.title or "Unknown bug"
        desc = bug.description or ""
        actual = bug.actual_behavior or ""
        expected = bug.expected_behavior or ""
        repro = "\n".join(bug.repro_steps) if bug.repro_steps else ""
        full_text = f"{title} {desc} {actual} {expected} {repro}"
        full_lower = full_text.lower()

        # ── Build summary from actual report fields ──
        summary_parts = []
        if title:
            summary_parts.append(title + ".")
        if desc:
            summary_parts.append(desc[:300])
        if actual:
            summary_parts.append(f"Actual behavior: {actual[:200]}")
        bug_summary = " ".join(summary_parts) or f"Bug report: {title}"

        # ── Extract symptoms ──
        symptoms = []
        if actual:
            symptoms.append(actual[:150])
        if expected:
            symptoms.append(f"Expected: {expected[:150]}")
        error_types = extract_error_types(full_text)
        for et in error_types[:3]:
            symptoms.append(et)
        http_codes = re.findall(r'\b(4\d{2}|5\d{2})\b', full_text)
        for code in list(dict.fromkeys(http_codes))[:2]:
            symptoms.append(f"HTTP {code} errors")
        if not symptoms:
            symptoms = [f"Bug: {title}"]

        # ── Classify bug type ──
        classification = classify_bug(full_text)

        # ── Generate targeted hypotheses ──
        hypotheses = []

        # Primary hypothesis from classification
        hypotheses.append(Hypothesis(
            description=(
                f"{classification.technical_term}: "
                f"{classification.description[:300]}"
            ),
            likelihood=classification.confidence / 100.0,
            category=HypothesisCategory.LOGIC_ERROR,
            supporting_evidence=[
                f"Bug title: {title}",
                f"Bug type classified as: {classification.bug_type}",
                f"Error types found: {', '.join(error_types[:3]) or 'none identified'}",
            ],
        ))

        # Secondary hypothesis — data validation
        if any(kw in full_lower for kw in ["negative", "invalid", "missing", "null", "overflow", "boundary"]):
            hypotheses.append(Hypothesis(
                description=(
                    "Missing input validation / boundary check: The system accepts "
                    "values outside the expected range, leading to invalid downstream state."
                ),
                likelihood=0.6,
                category=HypothesisCategory.DATA_VALIDATION,
                supporting_evidence=[
                    f"Bug mentions boundary-related terms",
                    f"Actual: {actual[:80]}" if actual else "No actual behavior given",
                ],
            ))

        # Tertiary hypothesis — deployment/config
        if any(kw in full_lower for kw in ["deploy", "version", "config", "release", "update", "v2", "v3"]):
            hypotheses.append(Hypothesis(
                description=(
                    "Deployment regression: The bug was introduced by a recent deployment. "
                    "The new code may have removed a previous protection or guard clause."
                ),
                likelihood=0.4,
                category=HypothesisCategory.CONFIGURATION,
                supporting_evidence=[
                    "Bug text mentions deployment/version changes",
                    f"Title: {title}",
                ],
            ))

        hypotheses.sort(key=lambda h: h.likelihood, reverse=True)

        # ── Extract affected components ──
        affected = extract_file_references(full_text)
        if not affected:
            affected = ["See repo navigator output for affected files"]

        return TriageOutput(
            bug_title=title,
            bug_summary=bug_summary,
            severity=bug.severity.value,
            symptoms=symptoms,
            hypotheses=hypotheses,
            affected_components=affected[:8],
            prior_reports_found=prior_reports,
            runbooks_found=runbooks,
        )

    def get_fallback_output(self, error: str) -> TriageOutput:
        return TriageOutput(
            bug_title=f"Triage failed: {error}",
            bug_summary=error,
            severity="UNKNOWN",
        )
