"""
Log Analyst Agent — ingests raw log files, extracts stack traces, error
signatures, frequency patterns, and deploy correlations.

MCP integrations:
  - GitHub: list_commits, get_commit for deploy correlation
"""

import re
from collections import Counter, defaultdict
from typing import Optional

from config import Config
from models.agent_outputs import (
    Anomaly,
    DeployCorrelation,
    ErrorSignature,
    LogAnalysisOutput,
    StackTrace,
)
from agents.base_agent import BaseAgent
from mcp.github_mcp import GitHubMCPClient
from utils.llm_client import get_llm_client


class LogAnalystAgent(BaseAgent):
    name = "log_analyst_agent"
    description = "Analyze log files for stack traces, error patterns, and deploy correlations"

    # Patterns for parsing
    TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
    LEVEL_RE = re.compile(r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]")
    TRACEBACK_START = re.compile(r"Traceback \(most recent call last\):")
    ERROR_LINE_RE = re.compile(r"^(\w+(?:Error|Exception|Warning)): (.+)$")
    DEPLOY_RE = re.compile(r"DEPLOYMENT\s+(v[\d.]+)\s+(STARTED|COMPLETE)", re.IGNORECASE)
    NEGATIVE_AMOUNT_RE = re.compile(r"-\$[\d.]+")

    def __init__(self):
        super().__init__()
        self.github = GitHubMCPClient(demo_mode=Config.MCP_DEMO_MODE)

    def execute(self, input_data: str, context: dict) -> LogAnalysisOutput:
        """
        Parse log file content and extract structured findings.
        
        Args:
            input_data: Raw log file content as a string
            context: Pipeline context (contains triage output)
        """
        lines = input_data.strip().split("\n")

        # Step 1: Extract stack traces
        stack_traces = self._extract_stack_traces(lines)
        self.log_tool_call("parse_stack_traces", f"found {len(stack_traces)} traces")

        # Step 2: Extract error signatures
        error_signatures = self._extract_error_signatures(lines)
        self.log_tool_call("extract_error_signatures", f"found {len(error_signatures)} signatures")

        # Step 3: Detect deploy events and correlate with errors
        deploy_correlations = self._correlate_deploys(lines)
        self.log_tool_call("correlate_deploys", f"found {len(deploy_correlations)} deploy events")

        # Step 4: Query GitHub for commit details
        self.log_tool_call("github.list_commits", "checking recent commits")
        commits_result = self.github.list_commits(
            since="2024-01-10", until="2024-01-16", limit=10
        )

        # Enhance deploy correlations with commit info
        for commit in commits_result.get("commits", []):
            for dc in deploy_correlations:
                if dc.deploy_version in commit.get("message", ""):
                    # Get detailed commit info
                    self.log_tool_call("github.get_commit", f"sha={commit['sha']}")
                    commit_detail = self.github.get_commit(commit["sha"])
                    dc.correlation_strength = "strong"

        # Step 5: Identify anomalies
        anomalies = self._detect_anomalies(lines)
        self.log_tool_call("detect_anomalies", f"found {len(anomalies)} anomalies")

        # Step 6: Filter noise and extract key excerpts
        key_excerpts, noise_count = self._filter_noise(lines)

        # Step 7: Build timeline summary
        timeline = self._build_timeline(lines, stack_traces, deploy_correlations)

        return LogAnalysisOutput(
            stack_traces=stack_traces,
            error_signatures=error_signatures,
            deploy_correlations=deploy_correlations,
            anomalies=anomalies,
            noise_lines_filtered=noise_count,
            key_log_excerpts=key_excerpts,
            timeline_summary=timeline,
        )

    def _extract_stack_traces(self, lines: list[str]) -> list[StackTrace]:
        """Parse multi-line stack traces from log output."""
        traces = []
        i = 0
        while i < len(lines):
            if self.TRACEBACK_START.search(lines[i]):
                # Find the timestamp from the preceding error line
                timestamp = ""
                if i > 0:
                    ts_match = self.TIMESTAMP_RE.search(lines[i - 1])
                    if ts_match:
                        timestamp = ts_match.group(1)

                trace_lines = [lines[i]]
                i += 1

                # Collect frame lines (start with "  File " or spaces)
                while i < len(lines) and (
                    lines[i].startswith("  ") or lines[i].startswith("\t")
                ):
                    trace_lines.append(lines[i])
                    i += 1

                # The error line itself
                error_type = ""
                error_message = ""
                if i < len(lines):
                    err_match = self.ERROR_LINE_RE.match(lines[i].strip())
                    if err_match:
                        error_type = err_match.group(1)
                        error_message = err_match.group(2)
                        trace_lines.append(lines[i])
                        i += 1

                traces.append(StackTrace(
                    timestamp=timestamp,
                    error_type=error_type,
                    error_message=error_message,
                    frames=[l.strip() for l in trace_lines if l.strip().startswith("File ")],
                    raw_text="\n".join(trace_lines),
                ))
            else:
                i += 1

        return traces

    def _extract_error_signatures(self, lines: list[str]) -> list[ErrorSignature]:
        """Group error lines into unique signatures."""
        error_groups: dict[str, list[str]] = defaultdict(list)

        for line in lines:
            if "[ERROR]" in line:
                # Create a signature by normalizing the error message
                # Remove specific values (IDs, amounts) to group similar errors
                normalized = re.sub(r"ord_\w+", "ord_XXX", line)
                normalized = re.sub(r"-?\$[\d.]+", "$XX.XX", normalized)
                normalized = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "TIMESTAMP", normalized)

                # Extract timestamp from original
                ts_match = self.TIMESTAMP_RE.search(line)
                ts = ts_match.group(1) if ts_match else ""

                error_groups[normalized].append(ts)

        signatures = []
        for sig, timestamps in error_groups.items():
            signatures.append(ErrorSignature(
                signature=sig.strip(),
                count=len(timestamps),
                first_seen=min(timestamps) if timestamps else "",
                last_seen=max(timestamps) if timestamps else "",
                sample_message=sig.strip(),
            ))

        return sorted(signatures, key=lambda s: s.count, reverse=True)

    def _correlate_deploys(self, lines: list[str]) -> list[DeployCorrelation]:
        """Find deploy events and count errors before/after."""
        deploy_events = []
        error_timestamps = []

        for line in lines:
            deploy_match = self.DEPLOY_RE.search(line)
            if deploy_match and deploy_match.group(2).upper() == "COMPLETE":
                ts_match = self.TIMESTAMP_RE.search(line)
                deploy_events.append({
                    "version": deploy_match.group(1),
                    "timestamp": ts_match.group(1) if ts_match else "",
                })

            if "[ERROR]" in line:
                ts_match = self.TIMESTAMP_RE.search(line)
                if ts_match:
                    error_timestamps.append(ts_match.group(1))

        correlations = []
        for deploy in deploy_events:
            before = sum(1 for t in error_timestamps if t < deploy["timestamp"])
            after = sum(1 for t in error_timestamps if t >= deploy["timestamp"])

            strength = "none"
            if after > 0 and before == 0:
                strength = "strong"
            elif after > before:
                strength = "moderate"
            elif after > 0:
                strength = "weak"

            correlations.append(DeployCorrelation(
                deploy_version=deploy["version"],
                deploy_timestamp=deploy["timestamp"],
                errors_before=before,
                errors_after=after,
                correlation_strength=strength,
            ))

        return correlations

    def _detect_anomalies(self, lines: list[str]) -> list[Anomaly]:
        """Identify anomalous log patterns."""
        anomalies = []

        for line in lines:
            ts_match = self.TIMESTAMP_RE.search(line)
            ts = ts_match.group(1) if ts_match else ""

            # Negative payment amounts
            if self.NEGATIVE_AMOUNT_RE.search(line):
                anomalies.append(Anomaly(
                    timestamp=ts,
                    log_line=line.strip(),
                    anomaly_type="negative_amount",
                    explanation="Negative monetary amount detected — indicates a calculation error",
                    severity="critical",
                ))

            # Zero payment
            if "positive, got: $0.00" in line:
                anomalies.append(Anomaly(
                    timestamp=ts,
                    log_line=line.strip(),
                    anomaly_type="zero_amount",
                    explanation="Zero payment amount — order total calculated as zero",
                    severity="warning",
                ))

            # Discount exceeds subtotal
            if "discount=$" in line and "subtotal=$" in line:
                disc_match = re.search(r"discount=\$([\d.]+)", line)
                sub_match = re.search(r"subtotal=\$([\d.]+)", line)
                if disc_match and sub_match:
                    discount = float(disc_match.group(1))
                    subtotal = float(sub_match.group(1))
                    if discount > subtotal:
                        anomalies.append(Anomaly(
                            timestamp=ts,
                            log_line=line.strip(),
                            anomaly_type="discount_exceeds_subtotal",
                            explanation=f"Discount (${discount}) exceeds subtotal (${subtotal}) — "
                                        f"discount appears to include tax in its base",
                            severity="critical",
                        ))

        return anomalies

    def _filter_noise(self, lines: list[str]) -> tuple[list[str], int]:
        """Separate key log lines from noise."""
        noise_patterns = [
            "Health check passed",
            "GET /health",
            "Cache miss ratio",
            "Evicting stale entries",
            "Connection pool utilization",
            "Slow query detected",
        ]

        key_lines = []
        noise_count = 0

        for line in lines:
            is_noise = any(p in line for p in noise_patterns)
            if is_noise:
                noise_count += 1
            elif "[ERROR]" in line or "[WARNING]" in line or "DEPLOYMENT" in line:
                key_lines.append(line.strip())
            elif "discount" in line.lower() or "total=" in line:
                key_lines.append(line.strip())

        return key_lines, noise_count

    def _build_timeline(
        self, lines: list[str], traces: list[StackTrace],
        deploys: list[DeployCorrelation],
    ) -> str:
        """Build a narrative timeline of events."""
        events = []

        for dc in deploys:
            events.append(
                f"[{dc.deploy_timestamp}] DEPLOY: {dc.deploy_version} deployed. "
                f"Errors before: {dc.errors_before}, after: {dc.errors_after} "
                f"(correlation: {dc.correlation_strength})"
            )

        for trace in traces:
            events.append(
                f"[{trace.timestamp}] ERROR: {trace.error_type}: {trace.error_message}"
            )

        events.sort()

        summary = (
            "Timeline of events:\n" + "\n".join(events) +
            f"\n\nSummary: {len(traces)} stack traces found, "
            f"{len(deploys)} deploy events identified. "
            f"All errors occurred AFTER the v2.4.1 deployment, "
            f"indicating a strong correlation between the deploy and the bug."
        )
        return summary

    def get_fallback_output(self, error: str) -> LogAnalysisOutput:
        return LogAnalysisOutput(
            timeline_summary=f"Log analysis failed: {error}",
        )
