"""
Pydantic models for parsing and validating bug reports.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BugReport(BaseModel):
    """Structured representation of a bug report parsed from Markdown."""

    title: str = Field(..., description="Short descriptive title of the bug")
    description: str = Field(..., description="Detailed description of the issue")
    expected_behavior: str = Field("", description="What should happen")
    actual_behavior: str = Field("", description="What actually happens")
    environment: dict = Field(
        default_factory=dict,
        description="Runtime environment details (Python version, OS, etc.)",
    )
    severity: Severity = Field(Severity.MEDIUM, description="Bug severity level")
    repro_steps: List[str] = Field(
        default_factory=list,
        description="Steps to reproduce (may be partial/incomplete)",
    )
    additional_context: str = Field(
        "", description="Any extra context from the reporter"
    )
    raw_text: str = Field("", description="Original Markdown source text")

    @classmethod
    def from_markdown(cls, markdown_text: str) -> "BugReport":
        """Parse a Markdown bug report into a structured BugReport object."""
        lines = markdown_text.strip().split("\n")
        
        title = ""
        description = ""
        expected = ""
        actual = ""
        severity = Severity.MEDIUM
        repro_steps = []
        environment = {}
        additional_context = ""

        current_section = None
        section_buffer = []

        def flush_section():
            nonlocal title, description, expected, actual, severity
            nonlocal repro_steps, environment, additional_context
            content = "\n".join(section_buffer).strip()
            if current_section is None and not title:
                title = content
            elif current_section == "title":
                title = content
            elif current_section == "description":
                description = content
            elif current_section == "severity":
                sev_text = content.upper().replace("*", "").strip()
                for s in Severity:
                    if s.value in sev_text:
                        severity = s
                        break
            elif current_section == "expected":
                expected = content
            elif current_section == "actual":
                actual = content
            elif current_section == "environment":
                for line in section_buffer:
                    line = line.strip().lstrip("- ")
                    if ":" in line and "**" in line:
                        key = line.split("**")[1].strip(": ")
                        val = line.split("**")[-1].strip().lstrip(": ")
                        environment[key] = val
                    elif ":" in line:
                        parts = line.split(":", 1)
                        environment[parts[0].strip()] = parts[1].strip()
            elif current_section == "repro":
                for line in section_buffer:
                    line = line.strip()
                    if line and (line[0].isdigit() or line.startswith("-")):
                        step = line.lstrip("0123456789.-) ").strip()
                        if step:
                            repro_steps.append(step)
            elif current_section == "additional" or current_section == "impact" or current_section == "context":
                if additional_context:
                    additional_context += "\n\n"
                additional_context += content
            section_buffer.clear()

        section_map = {
            "title": ["title"],
            "description": ["description"],
            "severity": ["severity"],
            "expected": ["expected behavior", "expected"],
            "actual": ["actual behavior", "actual"],
            "environment": ["environment", "env"],
            "repro": ["steps to reproduce", "reproduction", "repro"],
            "impact": ["impact"],
            "additional": ["additional context", "additional", "notes"],
            "context": ["context"],
        }

        for line in lines:
            stripped = line.strip()
            # Check if this is a section header
            if stripped.startswith("#"):
                flush_section()
                header = stripped.lstrip("# ").lower()
                current_section = None
                for section_key, keywords in section_map.items():
                    if any(kw in header for kw in keywords):
                        current_section = section_key
                        break
                if current_section is None:
                    # Treat unknown headers as title if we don't have one
                    if not title:
                        title = stripped.lstrip("# ").strip()
                    else:
                        current_section = "additional"
                continue
            section_buffer.append(line)

        flush_section()

        # If title wasn't found in a header, use first non-empty line
        if not title:
            for line in lines:
                stripped = line.strip().lstrip("# ")
                if stripped:
                    title = stripped
                    break

        return cls(
            title=title,
            description=description,
            expected_behavior=expected,
            actual_behavior=actual,
            environment=environment,
            severity=severity,
            repro_steps=repro_steps,
            additional_context=additional_context,
            raw_text=markdown_text,
        )
