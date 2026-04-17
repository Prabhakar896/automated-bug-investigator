"""
Fix Planner Agent — synthesizes all upstream evidence to produce a
root-cause hypothesis, patch approach, and validation plan.

MCP integrations:
  - GitHub: create_issue with structured bug report
  - Drive: upload_file to save investigation report
"""

from config import Config
from models.agent_outputs import (
    FixPlanOutput,
    PatchApproach,
    ValidationPlan,
)
from agents.base_agent import BaseAgent
from mcp.github_mcp import GitHubMCPClient
from mcp.drive_mcp import DriveMCPClient
from utils.llm_client import get_llm_client


class FixPlannerAgent(BaseAgent):
    name = "fix_planner_agent"
    description = "Synthesize evidence, determine root cause, plan the fix"

    def __init__(self):
        super().__init__()
        self.github = GitHubMCPClient(demo_mode=Config.MCP_DEMO_MODE)
        self.drive = DriveMCPClient(demo_mode=Config.MCP_DEMO_MODE)

    def execute(self, input_data: dict, context: dict) -> FixPlanOutput:
        """
        Synthesize triage + log evidence + repro results into a fix plan.
        """
        triage = context.get("triage_output")
        log_analysis = context.get("log_analysis_output")
        repro = context.get("reproduction_output")
        repo_nav = context.get("repo_navigator_output")

        # Step 1: Generate fix plan using LLM or deterministic logic
        llm = get_llm_client()
        fix_plan = self._generate_fix_plan(llm, triage, log_analysis, repro, repo_nav)

        # Step 2: Create GitHub issue
        issue_body = self._build_issue_body(fix_plan, triage, log_analysis, repro)
        self.log_tool_call("github.create_issue", fix_plan.root_cause_hypothesis[:50])
        issue_result = self.github.create_issue(
            title=f"[BUG] {triage.bug_title if triage else 'Negative payment amount on discount'}",
            body=issue_body,
            labels=["bug", "auto-triage", "payment", "P1"],
        )
        fix_plan.github_issue_created = True
        fix_plan.github_issue_url = issue_result.get("url", "")

        # Step 3: Upload report to Drive
        self.log_tool_call("drive.upload_file", "investigation_report.json")
        drive_result = self.drive.upload_file(
            file_name="investigation_report.json",
            content=fix_plan.model_dump_json(),
        )
        fix_plan.drive_report_url = drive_result.get("webViewLink", "")

        return fix_plan

    def _generate_fix_plan(self, llm, triage, log_analysis, repro, repo_nav) -> FixPlanOutput:
        """Generate the fix plan from evidence."""
        if llm.is_available:
            prompt = self._build_prompt(triage, log_analysis, repro, repo_nav)
            self.log_tool_call("llm.generate", "generating fix plan")
            response = llm.generate(
                prompt=prompt,
                system_instruction=(
                    "You are a senior software engineer performing root cause analysis. "
                    "Synthesize all provided evidence to determine the root cause, "
                    "propose a fix, and create a validation plan. Be specific about "
                    "files, functions, and line numbers."
                ),
                response_schema=FixPlanOutput,
            )
            try:
                return FixPlanOutput(**response)
            except Exception:
                pass

        return self._deterministic_fix_plan(triage, log_analysis, repro, repo_nav)

    def _deterministic_fix_plan(self, triage, log_analysis, repro, repo_nav) -> FixPlanOutput:
        """Deep analysis fix plan — analyzes actual code and evidence."""
        from utils.code_analyzer import (
            analyze_code, analyze_log_patterns, classify_bug,
            extract_file_references, build_specific_root_cause,
        )

        evidence = []
        bug_title = "Unknown bug"
        bug_summary = ""
        affected_files = []

        # ── Collect evidence from triage ──
        if triage:
            bug_title = triage.bug_title
            bug_summary = triage.bug_summary
            if triage.hypotheses:
                evidence.extend(triage.hypotheses[0].supporting_evidence)
            affected_files = list(triage.affected_components or [])

        # ── Collect evidence from log analysis ──
        error_info = []
        stack_traces = []
        if log_analysis:
            stack_traces = log_analysis.stack_traces
            for trace in stack_traces:
                error_info.append(f"{trace.error_type}: {trace.error_message}")
                evidence.append(f"Stack trace: {trace.error_type}: {trace.error_message}")
                for frame in trace.frames:
                    file_match = __import__("re").search(r'"([^"]+\.py)"', frame)
                    if file_match and file_match.group(1) not in affected_files:
                        affected_files.append(file_match.group(1))

            for anomaly in log_analysis.anomalies:
                if anomaly.severity == "critical":
                    evidence.append(f"Log anomaly: {anomaly.explanation}")

            for dc in log_analysis.deploy_correlations:
                if dc.correlation_strength in ("strong", "moderate"):
                    evidence.append(
                        f"Deploy {dc.deploy_version}: {dc.errors_before} errors before → "
                        f"{dc.errors_after} after (correlation: {dc.correlation_strength})"
                    )

        # ── Collect evidence from reproduction ──
        repro_status = "No reproduction test available"
        if repro:
            if repro.consistent_failure:
                evidence.append(
                    f"Reproduction test consistently fails: {repro.failure_count}/{repro.total_runs}"
                )
                repro_status = f"Consistently failing ({repro.failure_count}/{repro.total_runs})"
            else:
                repro_status = f"Inconsistent ({repro.failure_count}/{repro.total_runs} failures)"

        # ═══ DEEP CODE ANALYSIS ═══
        code_analyses = []
        if repo_nav and hasattr(repo_nav, "source_snippets") and repo_nav.source_snippets:
            for fpath, content in repo_nav.source_snippets.items():
                if content and not content.startswith("Error"):
                    analysis = analyze_code(content, fpath)
                    code_analyses.append(analysis)
                    # Add specific functions to affected files
                    for func in analysis.functions:
                        entry = f"{fpath} :: {func.signature} (lines {func.line_start}-{func.line_end})"
                        if entry not in affected_files:
                            affected_files.append(entry)
                    # Add detected patterns as evidence
                    for pattern in analysis.patterns:
                        evidence.append(f"Code pattern [{pattern.severity}]: {pattern.description}")

        # ═══ LOG PATTERN ANALYSIS ═══
        log_patterns = []
        if log_analysis and hasattr(log_analysis, "key_log_excerpts"):
            raw_log = "\n".join(log_analysis.key_log_excerpts)
            log_patterns = analyze_log_patterns(raw_log)
            for lp in log_patterns:
                if lp.severity == "critical":
                    evidence.append(f"Log pattern: {lp.description}")

        # ═══ BUG CLASSIFICATION ═══
        full_text = f"{bug_title} {bug_summary} {' '.join(error_info)}"
        classification = classify_bug(full_text, code_analyses, log_patterns)
        self.log_tool_call("classify_bug", f"type={classification.bug_type}, conf={classification.confidence}%")

        # ═══ BUILD ROOT CAUSE ═══
        root_cause = build_specific_root_cause(
            bug_title=bug_title,
            bug_summary=bug_summary,
            classification=classification,
            code_analyses=code_analyses,
            log_patterns=log_patterns,
            stack_traces=stack_traces,
        )

        # ═══ CONFIDENCE CALCULATION ═══
        confidence = classification.confidence
        # Boost for strong evidence
        if stack_traces:
            confidence += min(5, len(stack_traces) * 2)
        if repro and repro.consistent_failure:
            confidence += 8
        if code_analyses and any(a.patterns for a in code_analyses):
            confidence += 5
        if log_patterns and any(p.severity == "critical" for p in log_patterns):
            confidence += 3
        if len(evidence) >= 5:
            confidence += 2
        confidence = min(97, confidence)

        # ═══ AFFECTED FILES ═══
        # Clean up — extract just the file paths for files_impacted
        clean_files = []
        for f in affected_files:
            if "::" in f:
                clean_files.append(f)  # Keep the full reference
            elif f.endswith(".py"):
                clean_files.append(f)
            elif f.endswith("()"):
                clean_files.append(f)
        if not clean_files:
            # Fall back to extracting from bug text
            clean_files = extract_file_references(full_text) or ["Review source code for affected files"]

        # ═══ FIX APPROACH ═══
        approach_lines = []
        for i, fix in enumerate(classification.fix_approaches, 1):
            approach_lines.append(f"{i}. {fix}")
        approach = "\n".join(approach_lines)

        # ═══ TESTS ═══
        tests = [f"{name} — {desc}" for name, desc in classification.test_suggestions]

        # ═══ RISKS ═══
        risks = classification.specific_risks

        return FixPlanOutput(
            root_cause_hypothesis=root_cause,
            confidence_pct=confidence,
            supporting_evidence=evidence or [f"Bug report: {bug_title}"],
            patch=PatchApproach(
                description=f"Fix: {classification.technical_term} in {clean_files[0] if clean_files else 'source'}",
                files_impacted=clean_files[:8],
                approach=approach,
                risks=risks,
                estimated_effort=self._estimate_effort(classification, code_analyses),
            ),
            validation_plan=ValidationPlan(
                tests_to_add=tests,
                regression_checks=[
                    "Run full existing test suite — no regressions",
                    "Verify the repro test now PASSES after fix",
                    "Integration test for the affected flow end-to-end",
                    "Load test under concurrency to verify fix under stress",
                ],
                acceptance_criteria=(
                    "1. All new tests pass\n"
                    "2. All existing tests pass (no regressions)\n"
                    "3. Repro test passes after fix\n"
                    "4. No invalid state produced under concurrent load\n"
                    "5. Edge cases from review are all covered"
                ),
            ),
        )

    def _estimate_effort(self, classification, code_analyses) -> str:
        """Estimate effort based on bug complexity."""
        if not code_analyses:
            return "4-8 hours (code fix + tests + review) — needs source code access"
        total_funcs = sum(len(a.functions) for a in code_analyses)
        total_patterns = sum(len(a.patterns) for a in code_analyses)
        if total_patterns <= 1 and total_funcs <= 3:
            return "2-4 hours (targeted fix in 1-2 functions + unit tests + code review)"
        elif total_patterns <= 3:
            return "4-8 hours (multi-function fix + comprehensive tests + review + deploy)"
        else:
            return "1-2 days (complex fix across multiple functions + migration + extensive testing)"

    def _build_prompt(self, triage, log_analysis, repro, repo_nav) -> str:
        sections = []
        
        if triage:
            sections.append(f"""## Triage Summary
Bug: {triage.bug_title}
Summary: {triage.bug_summary}
Severity: {triage.severity}
Top Hypothesis: {triage.hypotheses[0].description if triage.hypotheses else 'N/A'}
Affected Components: {', '.join(triage.affected_components)}""")

        if log_analysis:
            traces_text = "\n".join(
                f"  {t.error_type}: {t.error_message}" for t in log_analysis.stack_traces[:3]
            )
            anomalies_text = "\n".join(
                f"  [{a.severity}] {a.explanation}" for a in log_analysis.anomalies[:5]
            )
            sections.append(f"""## Log Analysis
Stack Traces:
{traces_text}
Anomalies:
{anomalies_text}
Timeline: {log_analysis.timeline_summary[:300]}""")

        if repro:
            sections.append(f"""## Reproduction Results
Consistent failure: {repro.consistent_failure}
Failures: {repro.failure_count}/{repro.total_runs}
Exit code: {repro.exit_code}""")

        if repo_nav:
            chain = "\n".join(repo_nav.dependency_chain[:5])
            sections.append(f"""## Call Chain
{chain}""")

        return "\n\n".join(sections) + """

Based on ALL evidence above, produce:
1. Root cause hypothesis with confidence percentage
2. Specific patch approach (files, functions, changes)
3. Risks and estimated effort
4. Validation plan (tests to add, regression checks, acceptance criteria)
"""

    def _build_issue_body(self, fix_plan, triage, log_analysis, repro) -> str:
        """Build a formatted GitHub issue body."""
        repro_status = "✅ Consistent" if (repro and repro.consistent_failure) else "❌ Inconsistent"
        
        return f"""## Bug Summary
{triage.bug_summary if triage else 'See investigation report'}

## Root Cause Analysis (Automated)
**Confidence:** {fix_plan.confidence_pct}%

{fix_plan.root_cause_hypothesis}

## Evidence
{chr(10).join(f'- {e}' for e in fix_plan.supporting_evidence)}

## Reproduction
Status: {repro_status}
Command: `{repro.run_command if repro else 'N/A'}`

## Proposed Fix
{fix_plan.patch.approach}

### Files Impacted
{chr(10).join(f'- `{f}`' for f in fix_plan.patch.files_impacted)}

### Risks
{chr(10).join(f'- {r}' for r in fix_plan.patch.risks)}

---
*This issue was auto-generated by the Antigravity Bug Investigation Pipeline.*
"""

    def get_fallback_output(self, error: str) -> FixPlanOutput:
        return FixPlanOutput(
            root_cause_hypothesis=f"Fix planning failed: {error}",
            confidence_pct=0,
            patch=PatchApproach(description="Unable to determine — agent failed"),
        )
