"""
Automated Bug Investigation Pipeline — CLI Entry Point.

Usage:
  python main.py --bug-report inputs/bug_report.md --logs inputs/logs/app.log

Options:
  --bug-report  Path to the bug report markdown file
  --logs        Path to the application log file
  --output-dir  Output directory (default: ./output)
  --timeout     Agent timeout in seconds (default: 60)
  --log-level   Logging level (default: INFO)
  --demo-mode   Force demo mode for MCP integrations
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Automated Bug Investigation Pipeline — Antigravity Software",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --bug-report inputs/bug_report.md --logs inputs/logs/app.log
  python main.py --bug-report inputs/bug_report.md --logs inputs/logs/app.log --log-level DEBUG
  python main.py --bug-report inputs/bug_report.md --logs inputs/logs/app.log --timeout 120
        """,
    )
    parser.add_argument(
        "--bug-report",
        required=True,
        help="Path to the bug report markdown file",
    )
    parser.add_argument(
        "--logs",
        required=True,
        help="Path to the application log file",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory for investigation artifacts (default: ./output)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Agent timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--demo-mode",
        action="store_true",
        default=False,
        help="Force demo mode for MCP integrations (simulated responses)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Apply CLI args to environment/config
    if args.output_dir:
        os.environ["OUTPUT_DIR"] = args.output_dir
    if args.timeout:
        os.environ["AGENT_TIMEOUT_SECONDS"] = str(args.timeout)
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level
    if args.demo_mode:
        os.environ["MCP_DEMO_MODE"] = "true"

    # Import after env vars are set so Config picks them up
    from config import Config
    Config.ensure_directories()

    from utils.logger import setup_logging
    root_logger = setup_logging(
        log_level=args.log_level,
        log_dir=Config.LOG_DIR,
    )

    from models.bug_report import BugReport
    from orchestrator import Pipeline

    logger = root_logger

    # ─── Read Input Files ─────────────────────────────────
    bug_report_path = Path(args.bug_report)
    log_path = Path(args.logs)

    if not bug_report_path.exists():
        print(f"ERROR: Bug report file not found: {bug_report_path}")
        sys.exit(1)

    if not log_path.exists():
        print(f"ERROR: Log file not found: {log_path}")
        sys.exit(1)

    logger.info(f"[INPUT] Bug report: {bug_report_path.resolve()}")
    logger.info(f"[INPUT] Log file: {log_path.resolve()}")

    # Parse bug report
    bug_report_text = bug_report_path.read_text(encoding="utf-8")
    bug_report = BugReport.from_markdown(bug_report_text)
    logger.info(f"[PARSED] Bug report: {bug_report.title}")
    logger.info(f"   Severity: {bug_report.severity.value}")
    logger.info(f"   Repro steps: {len(bug_report.repro_steps)}")

    # Read log file
    log_content = log_path.read_text(encoding="utf-8")
    logger.info(f"[INPUT] Log file: {len(log_content)} characters, {log_content.count(chr(10))} lines")

    # ─── Run Pipeline ─────────────────────────────────────
    pipeline = Pipeline()
    report = pipeline.run(bug_report=bug_report, log_content=log_content)

    # ─── Print Final Summary ──────────────────────────────
    print("\n" + "=" * 60)
    print("INVESTIGATION COMPLETE")
    print("=" * 60)
    print(f"  Bug: {report.bug_summary.title}")
    print(f"  Severity: {report.bug_summary.severity}")
    print(f"  Confidence: {report.confidence_score}%")
    print(f"  Root Cause: {report.root_cause.hypothesis[:100]}...")
    print(f"")
    print(f"  [REPORT] {Config.OUTPUT_DIR}/investigation_report.json")
    print(f"  [REPRO]  {report.repro.artifact_path}")
    print(f"  [TRACE]  {Config.LOG_DIR}/agent_trace.log")
    print(f"")
    print(f"  MCP Actions:")
    print(f"    GitHub Issue: {report.mcp_actions_taken.github_issue_url or 'N/A'}")
    print(f"    Drive Report: {report.mcp_actions_taken.drive_report_url or 'N/A'}")
    print(f"    Calendar:     {report.mcp_actions_taken.calendar_event_id or 'N/A'}")
    print(f"    Email:        {report.mcp_actions_taken.email_sent_to or 'N/A'}")
    print("=" * 60)

    # Exit with success
    return 0


if __name__ == "__main__":
    sys.exit(main())
