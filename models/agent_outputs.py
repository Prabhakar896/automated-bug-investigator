"""
Pydantic models for all inter-agent data contracts.

Each agent produces a typed output that downstream agents can consume
with full type safety and validation.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Triage Agent Output ──────────────────────────────────────────

class HypothesisCategory(str, Enum):
    LOGIC_ERROR = "logic_error"
    DATA_VALIDATION = "data_validation"
    RACE_CONDITION = "race_condition"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    INTEGRATION = "integration"
    PERFORMANCE = "performance"
    SECURITY = "security"
    OTHER = "other"


class Hypothesis(BaseModel):
    """A single triage hypothesis about the root cause."""
    description: str = Field(..., description="What might be causing the bug")
    likelihood: float = Field(
        ..., ge=0, le=1, description="Probability estimate (0.0 to 1.0)"
    )
    category: HypothesisCategory = Field(
        HypothesisCategory.OTHER, description="Category of the hypothesis"
    )
    supporting_evidence: List[str] = Field(
        default_factory=list, description="Evidence supporting this hypothesis"
    )


class TriageOutput(BaseModel):
    """Output from the Triage Agent."""
    bug_title: str = Field(..., description="Cleaned/normalized bug title")
    bug_summary: str = Field(..., description="Concise summary of the bug")
    severity: str = Field("MEDIUM", description="Assessed severity")
    symptoms: List[str] = Field(
        default_factory=list, description="Observable symptoms"
    )
    hypotheses: List[Hypothesis] = Field(
        default_factory=list, description="Ranked list of root-cause hypotheses"
    )
    affected_components: List[str] = Field(
        default_factory=list, description="Components likely affected"
    )
    prior_reports_found: List[str] = Field(
        default_factory=list, description="Similar issues found via MCP search"
    )
    runbooks_found: List[str] = Field(
        default_factory=list, description="Relevant runbooks found via MCP search"
    )


# ─── Log Analyst Agent Output ────────────────────────────────────

class StackTrace(BaseModel):
    """A parsed stack trace from logs."""
    timestamp: str = Field("", description="When the error occurred")
    error_type: str = Field("", description="Exception class name")
    error_message: str = Field("", description="Exception message")
    frames: List[str] = Field(
        default_factory=list, description="Stack trace frames"
    )
    raw_text: str = Field("", description="Original stack trace text")


class ErrorSignature(BaseModel):
    """A unique error pattern found in logs."""
    signature: str = Field(..., description="Unique error identifier")
    count: int = Field(1, description="Number of occurrences")
    first_seen: str = Field("", description="First occurrence timestamp")
    last_seen: str = Field("", description="Last occurrence timestamp")
    sample_message: str = Field("", description="Representative error message")


class DeployCorrelation(BaseModel):
    """Correlation between a deploy event and error patterns."""
    deploy_version: str = Field("", description="Version that was deployed")
    deploy_timestamp: str = Field("", description="When deployment occurred")
    errors_before: int = Field(0, description="Error count before deploy")
    errors_after: int = Field(0, description="Error count after deploy")
    correlation_strength: str = Field(
        "none", description="none/weak/moderate/strong"
    )


class Anomaly(BaseModel):
    """An annotated anomaly found in logs."""
    timestamp: str = ""
    log_line: str = ""
    anomaly_type: str = ""  # e.g., "negative_amount", "error_spike"
    explanation: str = ""
    severity: str = "info"  # info/warning/critical


class LogAnalysisOutput(BaseModel):
    """Output from the Log Analyst Agent."""
    stack_traces: List[StackTrace] = Field(
        default_factory=list, description="Extracted stack traces"
    )
    error_signatures: List[ErrorSignature] = Field(
        default_factory=list, description="Unique error patterns"
    )
    deploy_correlations: List[DeployCorrelation] = Field(
        default_factory=list, description="Deploy-error correlations"
    )
    anomalies: List[Anomaly] = Field(
        default_factory=list, description="Annotated anomalies"
    )
    noise_lines_filtered: int = Field(
        0, description="Number of irrelevant lines filtered out"
    )
    key_log_excerpts: List[str] = Field(
        default_factory=list, description="Most important log lines"
    )
    timeline_summary: str = Field(
        "", description="Narrative of events in chronological order"
    )


# ─── Repo Navigator Agent Output ─────────────────────────────────

class FileInfo(BaseModel):
    """Information about a source file."""
    path: str = Field(..., description="File path relative to repo root")
    description: str = Field("", description="What this file does")
    relevance: str = Field(
        "low", description="Relevance to the bug: low/medium/high"
    )
    key_functions: List[str] = Field(
        default_factory=list, description="Important functions in this file"
    )


class RepoNavigatorOutput(BaseModel):
    """Output from the Repo Navigator Agent."""
    module_map: dict = Field(
        default_factory=dict, description="Map of modules and their purposes"
    )
    relevant_files: List[FileInfo] = Field(
        default_factory=list, description="Files relevant to the bug"
    )
    dependency_chain: List[str] = Field(
        default_factory=list, description="Call chain from entry point to bug"
    )
    source_snippets: dict = Field(
        default_factory=dict, description="Key source code snippets by file"
    )


# ─── Reproduction Agent Output ───────────────────────────────────

class ReproductionOutput(BaseModel):
    """Output from the Reproduction Agent."""
    repro_script_path: str = Field(
        "", description="Path to the generated repro test file"
    )
    repro_script_content: str = Field(
        "", description="Content of the generated repro test"
    )
    run_command: str = Field(
        "pytest repro/repro_test.py -v", description="Command to run the repro"
    )
    stdout: str = Field("", description="Captured stdout from execution")
    stderr: str = Field("", description="Captured stderr from execution")
    exit_code: int = Field(-1, description="Process exit code")
    consistent_failure: bool = Field(
        False, description="Whether the test fails consistently"
    )
    failure_count: int = Field(
        0, description="Number of times the test was run and failed"
    )
    total_runs: int = Field(
        0, description="Total number of test runs"
    )


# ─── Fix Planner Agent Output ────────────────────────────────────

class PatchApproach(BaseModel):
    """Details of the proposed patch."""
    description: str = Field(..., description="What the patch does")
    files_impacted: List[str] = Field(
        default_factory=list, description="Files that need changes"
    )
    approach: str = Field(
        "", description="Technical approach to fix"
    )
    risks: List[str] = Field(
        default_factory=list, description="Risks of this approach"
    )
    estimated_effort: str = Field(
        "", description="Estimated effort to implement"
    )


class ValidationPlan(BaseModel):
    """Plan for validating the fix."""
    tests_to_add: List[str] = Field(
        default_factory=list, description="New tests to write"
    )
    regression_checks: List[str] = Field(
        default_factory=list, description="Existing tests to verify still pass"
    )
    acceptance_criteria: str = Field(
        "", description="Criteria for accepting the fix"
    )


class FixPlanOutput(BaseModel):
    """Output from the Fix Planner Agent."""
    root_cause_hypothesis: str = Field(
        ..., description="Root cause hypothesis"
    )
    confidence_pct: float = Field(
        0, ge=0, le=100, description="Confidence percentage"
    )
    supporting_evidence: List[str] = Field(
        default_factory=list, description="Evidence supporting the hypothesis"
    )
    patch: PatchApproach = Field(
        default_factory=lambda: PatchApproach(description="TBD"),
        description="Proposed patch details",
    )
    validation_plan: ValidationPlan = Field(
        default_factory=ValidationPlan, description="Validation plan"
    )
    github_issue_created: bool = Field(
        False, description="Whether a GitHub issue was created"
    )
    github_issue_url: str = Field(
        "", description="URL of the created GitHub issue"
    )
    drive_report_url: str = Field(
        "", description="URL of the uploaded Drive report"
    )


# ─── Reviewer/Critic Agent Output ────────────────────────────────

class ReviewIssue(BaseModel):
    """An issue found by the reviewer."""
    category: str = Field(
        "", description="Category: repro_quality/evidence/edge_case/regression"
    )
    description: str = Field(..., description="Description of the issue")
    severity: str = Field("info", description="info/warning/critical")
    recommendation: str = Field("", description="Suggested action")


class ReviewOutput(BaseModel):
    """Output from the Reviewer/Critic Agent."""
    issues_found: List[ReviewIssue] = Field(
        default_factory=list, description="Issues identified in the analysis"
    )
    repro_quality_score: float = Field(
        0, ge=0, le=10, description="Quality score for the repro test (0-10)"
    )
    evidence_quality_score: float = Field(
        0, ge=0, le=10, description="Quality score for the evidence (0-10)"
    )
    root_cause_quality_score: float = Field(
        0, ge=0, le=10, description="Quality score for root-cause analysis (0-10)"
    )
    open_questions: List[str] = Field(
        default_factory=list, description="Questions that remain unanswered"
    )
    edge_cases: List[str] = Field(
        default_factory=list, description="Edge cases to consider"
    )
    overall_confidence_adjustment: float = Field(
        0, description="Adjustment to confidence (-20 to +10)"
    )
    approval_status: str = Field(
        "needs_revision", description="approved/needs_revision/rejected"
    )


# ─── Communication Agent Output ──────────────────────────────────

class MCPAction(BaseModel):
    """Record of an MCP action taken."""
    mcp_server: str = Field(..., description="Which MCP server was called")
    tool_name: str = Field(..., description="Tool name that was invoked")
    parameters: dict = Field(default_factory=dict, description="Call parameters")
    result: str = Field("", description="Result or status")
    success: bool = Field(True, description="Whether the call succeeded")


class CommunicationOutput(BaseModel):
    """Output from the Communication Agent."""
    actions_taken: List[MCPAction] = Field(
        default_factory=list, description="MCP actions executed"
    )
    github_issue_url: str = Field("", description="GitHub issue URL")
    drive_report_url: str = Field("", description="Drive report URL")
    calendar_event_id: str = Field("", description="Calendar event ID")
    email_sent_to: str = Field("", description="Email recipient")
    team_summary: str = Field(
        "", description="Human-readable summary for team handoff"
    )
    talent_search_performed: bool = Field(
        False, description="Whether a talent search was performed"
    )
