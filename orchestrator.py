"""
Pipeline Orchestrator — runs agents in a deterministic DAG.

Execution order:
  Triage → Log Analyst → Repo Navigator → Reproduction → Fix Planner → Reviewer → Communication

Each agent receives typed upstream outputs via the shared PipelineState.
Handles timeouts, retries, and graceful degradation.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional

from config import Config
from models.bug_report import BugReport
from models.investigation_report import (
    AgentTraceEntry,
    BugSummary,
    Evidence,
    InvestigationReport,
    MCPActionsTaken,
    PatchPlan,
    ReproInfo,
    RootCause,
    ValidationPlanReport,
)
from agents.triage_agent import TriageAgent
from agents.log_analyst_agent import LogAnalystAgent
from agents.repo_navigator_agent import RepoNavigatorAgent
from agents.reproduction_agent import ReproductionAgent
from agents.fix_planner_agent import FixPlannerAgent
from agents.reviewer_agent import ReviewerAgent
from agents.communication_agent import CommunicationAgent
from utils.logger import get_logger, setup_logging

logger = get_logger("orchestrator")


class PipelineState:
    """Shared state passed between agents."""

    def __init__(self):
        self.bug_report: Optional[BugReport] = None
        self.log_content: str = ""
        self.triage_output: Any = None
        self.log_analysis_output: Any = None
        self.repo_navigator_output: Any = None
        self.reproduction_output: Any = None
        self.fix_plan_output: Any = None
        self.review_output: Any = None
        self.communication_output: Any = None
        self.agent_traces: list[AgentTraceEntry] = []

    def as_context(self) -> dict:
        """Return current state as a dict for agent context."""
        return {
            "bug_report": self.bug_report,
            "triage_output": self.triage_output,
            "log_analysis_output": self.log_analysis_output,
            "repo_navigator_output": self.repo_navigator_output,
            "reproduction_output": self.reproduction_output,
            "fix_plan_output": self.fix_plan_output,
            "review_output": self.review_output,
            "communication_output": self.communication_output,
        }


class Pipeline:
    """
    DAG orchestrator that runs agents in sequence with error handling.
    
    Architecture:
      ┌────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────────┐
      │ Triage │ → │ LogAnalyst │ → │ RepoNavigator│ → │ Reproduction │
      └────────┘   └────────────┘   └──────────────┘   └──────────────┘
                                                               │
      ┌───────────────┐   ┌──────────┐   ┌─────────────┐      │
      │ Communication │ ← │ Reviewer │ ← │ Fix Planner │ ←────┘
      └───────────────┘   └──────────┘   └─────────────┘
    """

    def __init__(self):
        self.state = PipelineState()
        self.start_time = 0.0

    def run(self, bug_report: BugReport, log_content: str) -> InvestigationReport:
        """
        Execute the full investigation pipeline.

        Args:
            bug_report: Parsed bug report
            log_content: Raw log file content

        Returns:
            Complete investigation report
        """
        self.start_time = time.time()
        self.state.bug_report = bug_report
        self.state.log_content = log_content

        logger.info("=" * 60)
        logger.info(">> AUTOMATED BUG INVESTIGATION PIPELINE -- STARTING")
        logger.info("=" * 60)
        logger.info(f"Bug: {bug_report.title}")
        logger.info(f"Severity: {bug_report.severity.value}")
        logger.info(f"Config: {json.dumps(Config.summary(), indent=2)}")
        logger.info("")

        # ─── Stage 1: Triage ──────────────────────────────────
        self._run_stage("1/7", "TRIAGE", self._stage_triage)

        # ─── Stage 2: Log Analysis ────────────────────────────
        self._run_stage("2/7", "LOG ANALYSIS", self._stage_log_analysis)

        # ─── Stage 3: Repo Navigation ────────────────────────
        self._run_stage("3/7", "REPO NAVIGATION", self._stage_repo_navigation)

        # ─── Stage 4: Reproduction ────────────────────────────
        self._run_stage("4/7", "REPRODUCTION", self._stage_reproduction)

        # ─── Stage 5: Fix Planning ────────────────────────────
        self._run_stage("5/7", "FIX PLANNING", self._stage_fix_planning)

        # ─── Stage 6: Review ─────────────────────────────────
        self._run_stage("6/7", "REVIEW", self._stage_review)

        # ─── Stage 7: Communication ──────────────────────────
        self._run_stage("7/7", "COMMUNICATION", self._stage_communication)

        # ─── Assemble Final Report ────────────────────────────
        report = self._assemble_report()

        total_ms = int((time.time() - self.start_time) * 1000)
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"[DONE] PIPELINE COMPLETE -- Total time: {total_ms}ms")
        logger.info(f"   Confidence score: {report.confidence_score}%")
        logger.info(f"   Agents traced: {len(report.agents_trace)}")
        logger.info("=" * 60)

        return report

    def _run_stage(self, stage_num: str, stage_name: str, stage_fn):
        """Run a pipeline stage with logging."""
        logger.info(f"{'-' * 50}")
        logger.info(f">> Stage {stage_num}: {stage_name}")
        logger.info(f"{'-' * 50}")
        try:
            stage_fn()
        except Exception as e:
            logger.error(f"Stage {stage_name} failed catastrophically: {e}")
            logger.info(f"Continuing pipeline with partial data...")

    def _stage_triage(self):
        agent = TriageAgent()
        self.state.triage_output = agent.run(
            self.state.bug_report, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_log_analysis(self):
        agent = LogAnalystAgent()
        self.state.log_analysis_output = agent.run(
            self.state.log_content, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_repo_navigation(self):
        agent = RepoNavigatorAgent()
        self.state.repo_navigator_output = agent.run(
            {"src_dir": str(Config.SRC_DIR)}, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_reproduction(self):
        agent = ReproductionAgent()
        self.state.reproduction_output = agent.run(
            {}, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_fix_planning(self):
        agent = FixPlannerAgent()
        self.state.fix_plan_output = agent.run(
            {}, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_review(self):
        agent = ReviewerAgent()
        self.state.review_output = agent.run(
            {}, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _stage_communication(self):
        agent = CommunicationAgent()
        self.state.communication_output = agent.run(
            {}, self.state.as_context()
        )
        self.state.agent_traces.extend(agent.trace_entries)

    def _assemble_report(self) -> InvestigationReport:
        """Assemble the final investigation report from all agent outputs."""
        triage = self.state.triage_output
        logs = self.state.log_analysis_output
        repro = self.state.reproduction_output
        fix_plan = self.state.fix_plan_output
        review = self.state.review_output
        comm = self.state.communication_output

        # Calculate final confidence
        base_confidence = fix_plan.confidence_pct if fix_plan else 50
        adjustment = review.overall_confidence_adjustment if review else 0
        final_confidence = max(0, min(100, base_confidence + adjustment))

        report = InvestigationReport(
            bug_summary=BugSummary(
                title=triage.bug_title if triage else "Unknown",
                symptoms=triage.symptoms if triage else [],
                scope=", ".join(triage.affected_components[:3]) if triage else "",
                severity=triage.severity if triage else "HIGH",
            ),
            evidence=Evidence(
                log_excerpts=(logs.key_log_excerpts[:10] if logs else []),
                stack_traces=[
                    t.raw_text for t in (logs.stack_traces[:5] if logs else [])
                ],
                deploy_correlation=(
                    logs.timeline_summary[:500] if logs else ""
                ),
            ),
            repro=ReproInfo(
                artifact_path=repro.repro_script_path if repro else "",
                run_command=repro.run_command if repro else "",
                expected_output=(
                    f"FAIL — {repro.failure_count}/{repro.total_runs} runs failed"
                    if repro else ""
                ),
            ),
            root_cause=RootCause(
                hypothesis=fix_plan.root_cause_hypothesis if fix_plan else "",
                confidence_pct=final_confidence,
                supporting_evidence=(
                    fix_plan.supporting_evidence if fix_plan else []
                ),
            ),
            patch_plan=PatchPlan(
                files_impacted=fix_plan.patch.files_impacted if fix_plan else [],
                approach=fix_plan.patch.approach if fix_plan else "",
                risks=fix_plan.patch.risks if fix_plan else [],
                estimated_effort=fix_plan.patch.estimated_effort if fix_plan else "",
            ),
            validation_plan=ValidationPlanReport(
                tests_to_add=(
                    fix_plan.validation_plan.tests_to_add if fix_plan else []
                ),
                regression_checks=(
                    fix_plan.validation_plan.regression_checks if fix_plan else []
                ),
                acceptance_criteria=(
                    fix_plan.validation_plan.acceptance_criteria if fix_plan else ""
                ),
            ),
            mcp_actions_taken=MCPActionsTaken(
                github_issue_url=comm.github_issue_url if comm else "",
                drive_report_url=comm.drive_report_url if comm else "",
                calendar_event_id=comm.calendar_event_id if comm else "",
                email_sent_to=comm.email_sent_to if comm else "",
            ),
            open_questions=review.open_questions if review else [],
            edge_cases=review.edge_cases if review else [],
            confidence_score=final_confidence,
            agents_trace=self.state.agent_traces,
        )

        # Write outputs
        self._write_outputs(report)

        return report

    def _write_outputs(self, report: InvestigationReport):
        """Write all output artifacts to disk."""
        output_dir = Path(Config.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write investigation report
        report_path = output_dir / "investigation_report.json"
        report_json = report.model_dump_json(indent=2)
        report_path.write_text(report_json, encoding="utf-8")
        logger.info(f"[OUTPUT] Investigation report: {report_path}")

        # Write a human-readable summary
        summary_path = output_dir / "investigation_summary.md"
        summary_path.write_text(
            self._build_markdown_summary(report), encoding="utf-8"
        )
        logger.info(f"[OUTPUT] Human-readable summary: {summary_path}")

    def _build_markdown_summary(self, report: InvestigationReport) -> str:
        """Build a markdown summary of the investigation."""
        return f"""# Bug Investigation Report

## Bug Summary
- **Title:** {report.bug_summary.title}
- **Severity:** {report.bug_summary.severity}
- **Scope:** {report.bug_summary.scope}
- **Confidence:** {report.confidence_score}%

### Symptoms
{chr(10).join(f'- {s}' for s in report.bug_summary.symptoms)}

## Root Cause
**Hypothesis** (confidence: {report.root_cause.confidence_pct}%):

{report.root_cause.hypothesis}

### Supporting Evidence
{chr(10).join(f'- {e}' for e in report.root_cause.supporting_evidence)}

## Reproduction
- **Script:** `{report.repro.artifact_path}`
- **Run command:** `{report.repro.run_command}`
- **Expected:** {report.repro.expected_output}

## Patch Plan
**Approach:**
{report.patch_plan.approach}

**Files impacted:**
{chr(10).join(f'- `{f}`' for f in report.patch_plan.files_impacted)}

**Risks:**
{chr(10).join(f'- {r}' for r in report.patch_plan.risks)}

**Estimated effort:** {report.patch_plan.estimated_effort}

## Validation Plan
### Tests to Add
{chr(10).join(f'- {t}' for t in report.validation_plan.tests_to_add)}

### Regression Checks
{chr(10).join(f'- {r}' for r in report.validation_plan.regression_checks)}

### Acceptance Criteria
{report.validation_plan.acceptance_criteria}

## MCP Actions Taken
- **GitHub Issue:** {report.mcp_actions_taken.github_issue_url or 'N/A'}
- **Drive Report:** {report.mcp_actions_taken.drive_report_url or 'N/A'}
- **Calendar Event:** {report.mcp_actions_taken.calendar_event_id or 'N/A'}
- **Email Sent To:** {report.mcp_actions_taken.email_sent_to or 'N/A'}

## Open Questions
{chr(10).join(f'- {q}' for q in report.open_questions)}

## Agent Trace Summary
| Agent | Status | Duration |
|-------|--------|----------|
{chr(10).join(f'| {t.agent_name} | {t.status} | {t.duration_ms}ms |' for t in report.agents_trace)}

---
*Generated by Antigravity Bug Investigation Pipeline*
"""
