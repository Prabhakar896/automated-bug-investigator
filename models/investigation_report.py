"""
Final investigation report model — matches the required output JSON schema.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class BugSummary(BaseModel):
    title: str = ""
    symptoms: List[str] = Field(default_factory=list)
    scope: str = ""
    severity: str = ""


class Evidence(BaseModel):
    log_excerpts: List[str] = Field(default_factory=list)
    stack_traces: List[str] = Field(default_factory=list)
    deploy_correlation: str = ""


class ReproInfo(BaseModel):
    artifact_path: str = ""
    run_command: str = ""
    expected_output: str = ""


class RootCause(BaseModel):
    hypothesis: str = ""
    confidence_pct: float = 0
    supporting_evidence: List[str] = Field(default_factory=list)


class PatchPlan(BaseModel):
    files_impacted: List[str] = Field(default_factory=list)
    approach: str = ""
    risks: List[str] = Field(default_factory=list)
    estimated_effort: str = ""


class ValidationPlanReport(BaseModel):
    tests_to_add: List[str] = Field(default_factory=list)
    regression_checks: List[str] = Field(default_factory=list)
    acceptance_criteria: str = ""


class MCPActionsTaken(BaseModel):
    github_issue_url: str = ""
    drive_report_url: str = ""
    calendar_event_id: str = ""
    email_sent_to: str = ""


class AgentTraceEntry(BaseModel):
    agent_name: str = ""
    step: str = ""
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: int = 0
    tool_calls: List[str] = Field(default_factory=list)
    status: str = "success"  # success/failed/timeout


class InvestigationReport(BaseModel):
    """
    Final structured investigation report.
    
    Matches the exact JSON schema required by the evaluation criteria.
    """
    bug_summary: BugSummary = Field(default_factory=BugSummary)
    evidence: Evidence = Field(default_factory=Evidence)
    repro: ReproInfo = Field(default_factory=ReproInfo)
    root_cause: RootCause = Field(default_factory=RootCause)
    patch_plan: PatchPlan = Field(default_factory=PatchPlan)
    validation_plan: ValidationPlanReport = Field(
        default_factory=ValidationPlanReport
    )
    mcp_actions_taken: MCPActionsTaken = Field(
        default_factory=MCPActionsTaken
    )
    open_questions: List[str] = Field(default_factory=list)
    edge_cases: List[str] = Field(default_factory=list)
    confidence_score: float = Field(0, ge=0, le=100)
    agents_trace: List[AgentTraceEntry] = Field(default_factory=list)
