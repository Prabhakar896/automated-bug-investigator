"""
Reviewer/Critic Agent — challenges every upstream agent's conclusions.

Evaluates:
  - Is the repro truly minimal and consistently failing?
  - Is the root-cause hypothesis well-evidenced?
  - Are there edge cases or regressions the patch might introduce?
  - Flags open questions for the team

No MCP integrations — pure internal reasoning.
"""

from models.agent_outputs import (
    ReviewIssue,
    ReviewOutput,
)
from agents.base_agent import BaseAgent
from utils.llm_client import get_llm_client


class ReviewerAgent(BaseAgent):
    name = "reviewer_agent"
    description = "Challenge all upstream findings, identify gaps, adjust confidence"

    def execute(self, input_data: dict, context: dict) -> ReviewOutput:
        """
        Review all upstream outputs and produce a critical assessment.
        """
        triage = context.get("triage_output")
        log_analysis = context.get("log_analysis_output")
        repro = context.get("reproduction_output")
        fix_plan = context.get("fix_plan_output")
        repo_nav = context.get("repo_navigator_output")

        llm = get_llm_client()

        if llm.is_available:
            return self._llm_review(llm, context)

        return self._deterministic_review(triage, log_analysis, repro, fix_plan)

    def _llm_review(self, llm, context: dict) -> ReviewOutput:
        """Use LLM for critical review."""
        prompt = self._build_review_prompt(context)
        self.log_tool_call("llm.generate", "generating review")
        response = llm.generate(
            prompt=prompt,
            system_instruction=(
                "You are a senior staff engineer performing a critical review of an "
                "automated bug investigation. Your job is to find weaknesses, gaps, "
                "and risks in the analysis. Be constructive but thorough. "
                "Rate each aspect on a 0-10 scale."
            ),
            response_schema=ReviewOutput,
        )
        try:
            return ReviewOutput(**response)
        except Exception:
            return self._deterministic_review(
                context.get("triage_output"),
                context.get("log_analysis_output"),
                context.get("reproduction_output"),
                context.get("fix_plan_output"),
            )

    def _deterministic_review(self, triage, log_analysis, repro, fix_plan) -> ReviewOutput:
        """Deterministic critical review."""
        issues = []
        open_questions = []
        edge_cases = []

        # ─── Review Repro Quality ─────────────────────────
        repro_score = 5.0
        if repro:
            if repro.consistent_failure:
                repro_score = 8.0
                issues.append(ReviewIssue(
                    category="repro_quality",
                    description="Repro test consistently fails — good signal",
                    severity="info",
                    recommendation="Consider adding parameterized tests with varied inputs",
                ))
            else:
                repro_score = 4.0
                issues.append(ReviewIssue(
                    category="repro_quality",
                    description="Repro test does not fail consistently",
                    severity="warning",
                    recommendation="Add more test variations to improve reliability",
                ))

            if repro.repro_script_content and len(repro.repro_script_content) > 3000:
                repro_score -= 1
                issues.append(ReviewIssue(
                    category="repro_quality",
                    description="Repro script is longer than expected for a 'minimal' test",
                    severity="info",
                    recommendation="Consider splitting into smaller, focused test cases",
                ))
        else:
            repro_score = 0
            issues.append(ReviewIssue(
                category="repro_quality",
                description="No repro test was generated",
                severity="critical",
                recommendation="Run reproduction agent again with more context",
            ))

        # ─── Review Evidence Quality ─────────────────────
        evidence_score = 5.0
        if log_analysis:
            if log_analysis.stack_traces:
                evidence_score += 2
            if log_analysis.deploy_correlations:
                for dc in log_analysis.deploy_correlations:
                    if dc.correlation_strength in ("strong", "moderate"):
                        evidence_score += 1
            if log_analysis.anomalies:
                critical_anomalies = [a for a in log_analysis.anomalies if a.severity == "critical"]
                if critical_anomalies:
                    evidence_score += 1

            if log_analysis.noise_lines_filtered > 0:
                issues.append(ReviewIssue(
                    category="evidence",
                    description=f"{log_analysis.noise_lines_filtered} noise lines successfully filtered",
                    severity="info",
                    recommendation="Verify no relevant lines were incorrectly classified as noise",
                ))
        
        evidence_score = min(10, evidence_score)

        # ─── Review Root Cause ────────────────────────────
        rc_score = 5.0
        if fix_plan:
            if fix_plan.confidence_pct >= 80:
                rc_score = 8.0
            elif fix_plan.confidence_pct >= 50:
                rc_score = 6.0

            if len(fix_plan.supporting_evidence) >= 3:
                rc_score += 1

            if fix_plan.patch.risks:
                issues.append(ReviewIssue(
                    category="regression",
                    description=f"Patch risks: {fix_plan.patch.risks[0][:100]}",
                    severity="warning",
                    recommendation=f"Mitigation: {fix_plan.patch.risks[1][:100] if len(fix_plan.patch.risks) > 1 else 'Run full regression suite'}",
                ))

            # ─── Edge cases from bug classification ───
            from utils.code_analyzer import classify_bug
            full_text = f"{triage.bug_title if triage else ''} {triage.bug_summary if triage else ''}"
            classification = classify_bug(full_text)

            edge_cases = list(classification.edge_cases[:5]) if classification.edge_cases else []
            if fix_plan and fix_plan.patch.files_impacted:
                for f in fix_plan.patch.files_impacted[:2]:
                    edge_cases.append(f"Verify fix doesn't break other flows in: {f}")

            # ─── Open questions from investigation ───
            open_questions = []
            if triage:
                open_questions.append(
                    f"Is '{triage.bug_title}' the only manifestation, or are there related issues?"
                )
            if log_analysis and log_analysis.deploy_correlations:
                for dc in log_analysis.deploy_correlations:
                    open_questions.append(
                        f"Was deploy {dc.deploy_version} the only change, or were there config changes too?"
                    )
            if fix_plan and fix_plan.patch.risks:
                for risk in fix_plan.patch.risks[:2]:
                    open_questions.append(f"Risk mitigation needed: {risk[:80]}")
            open_questions.append("How many existing records were affected and need correction?")
            open_questions.append("Should monitoring/alerting be added for this class of bug?")
        
        rc_score = min(10, rc_score)

        # ─── Calculate Confidence Adjustment ──────────────
        avg_score = (repro_score + evidence_score + rc_score) / 3
        if avg_score >= 8:
            confidence_adj = 5.0
        elif avg_score >= 6:
            confidence_adj = 0.0
        else:
            confidence_adj = -10.0

        approval = "approved" if avg_score >= 7 else "needs_revision"

        return ReviewOutput(
            issues_found=issues,
            repro_quality_score=repro_score,
            evidence_quality_score=evidence_score,
            root_cause_quality_score=rc_score,
            open_questions=open_questions,
            edge_cases=edge_cases,
            overall_confidence_adjustment=confidence_adj,
            approval_status=approval,
        )

    def _build_review_prompt(self, context: dict) -> str:
        """Build LLM prompt for review."""
        sections = []

        triage = context.get("triage_output")
        if triage:
            sections.append(f"Triage: {triage.bug_summary}\nHypotheses: {len(triage.hypotheses)}")

        log_analysis = context.get("log_analysis_output")
        if log_analysis:
            sections.append(
                f"Log Analysis: {len(log_analysis.stack_traces)} traces, "
                f"{len(log_analysis.anomalies)} anomalies"
            )

        repro = context.get("reproduction_output")
        if repro:
            sections.append(
                f"Repro: consistent_failure={repro.consistent_failure}, "
                f"failures={repro.failure_count}/{repro.total_runs}"
            )

        fix_plan = context.get("fix_plan_output")
        if fix_plan:
            sections.append(
                f"Fix Plan: confidence={fix_plan.confidence_pct}%, "
                f"root_cause={fix_plan.root_cause_hypothesis[:200]}"
            )

        return """Critically review this automated bug investigation:

""" + "\n\n".join(sections) + """

Evaluate:
1. Is the repro test truly minimal? Score 0-10.
2. Is the evidence sufficient? Score 0-10.
3. Is the root-cause hypothesis well-evidenced? Score 0-10.
4. What edge cases might the proposed patch miss?
5. What open questions remain?
6. Overall confidence adjustment (-20 to +10)?
7. Approval status: approved / needs_revision / rejected
"""

    def get_fallback_output(self, error: str) -> ReviewOutput:
        return ReviewOutput(
            issues_found=[
                ReviewIssue(
                    category="system",
                    description=f"Review agent failed: {error}",
                    severity="warning",
                    recommendation="Manual review required",
                )
            ],
            approval_status="needs_revision",
        )
