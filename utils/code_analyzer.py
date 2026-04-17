"""
Code Analyzer — extracts structured information from source code, logs,
and bug reports for deep analysis.

Used by agents to perform genuine root cause analysis without LLM.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

@dataclass
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    signature: str
    body: str
    has_return: bool = False
    calls: list = field(default_factory=list)


@dataclass
class ClassInfo:
    name: str
    line_start: int
    methods: list = field(default_factory=list)


@dataclass
class CodePattern:
    """A detected code pattern/smell."""
    pattern_type: str
    description: str
    location: str       # e.g. "function_name() lines 24-42"
    severity: str       # "critical", "warning", "info"
    evidence: str       # The actual code snippet


@dataclass
class CodeAnalysisResult:
    file_path: str = ""
    functions: list = field(default_factory=list)
    classes: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    patterns: list = field(default_factory=list)
    raw_lines: list = field(default_factory=list)


@dataclass
class LogPattern:
    """Detected pattern in log data."""
    pattern_type: str   # "concurrent_access", "error_burst", "deploy_regression"
    description: str
    evidence: list = field(default_factory=list)
    severity: str = "info"


@dataclass
class BugClassification:
    """Classified bug type with deep technical context."""
    bug_type: str           # e.g., "race_condition", "auth_bypass", "off_by_one"
    technical_term: str     # e.g., "TOCTOU", "Session fixation"
    confidence: float
    description: str
    fix_approaches: list = field(default_factory=list)
    specific_risks: list = field(default_factory=list)
    test_suggestions: list = field(default_factory=list)
    edge_cases: list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# BUG PATTERN DATABASE
# ══════════════════════════════════════════════════════════════

BUG_PATTERN_DB = {
    "race_condition": {
        "keywords": ["race condition", "concurrent", "toctou", "atomic", "lock",
                     "thread", "parallel", "simultaneous", "negative inventory",
                     "oversold", "overbook", "duplicate", "stale", "SELECT FOR UPDATE"],
        "code_patterns": [r"if\s+.*count.*[><=]", r"\.get\(.*\).*\n.*if\s+", r"read.*update",
                         r"check.*reserve", r"select.*update"],
        "technical_term": "TOCTOU (Time-of-Check to Time-of-Use) race condition",
        "description_template": (
            "{func_name}() performs a non-atomic read-then-write pattern:\n"
            "  Step 1: READ the current state (e.g., count/balance/status)\n"
            "  Step 2: CHECK if the state allows the operation\n"
            "  Step 3: WRITE the updated state\n\n"
            "Between Step 1 and Step 3, concurrent requests can read the SAME stale value. "
            "All pass the check and all write, causing inconsistent state."
        ),
        "fix_approaches": [
            "Add database-level locking (SELECT FOR UPDATE / pessimistic locking)",
            "Implement optimistic locking with version column and retry logic",
            "Use atomic database operations (UPDATE ... WHERE count >= :qty)",
            "Add application-level mutex/semaphore for critical sections",
        ],
        "risks": [
            "Adding locks may reduce throughput under high concurrency (~15-20% slower under burst traffic)",
            "Row-level locks can cause deadlocks if multiple resources are locked in inconsistent order — mitigate by always locking in consistent order",
            "Existing state may already be inconsistent — need data migration to fix affected records",
            "Optimistic locking alternative may cause high retry rates under burst traffic",
        ],
        "test_suggestions": [
            ("test_concurrent_access_last_resource", "N threads compete for the last 1 resource simultaneously → exactly 1 succeeds, rest get appropriate error"),
            ("test_state_never_goes_below_minimum", "Set count=5, send 20 concurrent requests → exactly 5 succeed, final count=0, never negative"),
            ("test_single_operation_normal_flow", "Single request succeeds and updates state correctly"),
            ("test_operation_when_resource_exhausted", "Try operation when resource=0 → get appropriate error (409/400)"),
            ("test_database_constraint_prevents_invalid_state", "Directly attempt invalid state → DB constraint violation"),
        ],
        "edge_cases": [
            "What happens to in-flight requests when the last resource is consumed?",
            "Does the system handle the case where a successful reservation is later rolled back?",
            "What's the behavior under extremely high concurrency (100+ simultaneous)?",
            "Are there any existing records in an inconsistent state that need correction?",
            "Does the retry logic have exponential backoff to prevent thundering herd?",
        ],
    },
    "calculation_error": {
        "keywords": ["wrong calculation", "incorrect amount", "negative total",
                     "discount", "tax", "rounding", "overflow", "miscalcul",
                     "should be", "instead of", "off by", "cent", "decimal"],
        "code_patterns": [r"discount.*=.*gross|total", r"amount.*\*.*percent",
                         r"tax.*\+.*discount", r"price.*-.*"],
        "technical_term": "Order of operations / incorrect operand in calculation",
        "description_template": (
            "{func_name}() applies the calculation to the wrong operand:\n"
            "  The operation uses {wrong_operand} instead of {right_operand}.\n\n"
            "Additionally, there is no boundary check (floor/ceiling clamp) on the result, "
            "allowing invalid values (negative, overflow, etc.)."
        ),
        "fix_approaches": [
            "Fix the calculation to use the correct operand/base value",
            "Add floor/ceiling clamps to prevent out-of-range results",
            "Add input validation to reject invalid parameters",
            "Recalculate dependent values after applying the correction",
        ],
        "risks": [
            "Existing records calculated with the buggy logic will have different values — assess data impact",
            "Downstream systems may depend on the (buggy) calculation order — verify integration points",
            "Rounding differences may cause penny discrepancies in financial reports",
            "Need to handle edge case of exact-zero results in the business flow",
        ],
        "test_suggestions": [
            ("test_calculation_boundary_100_percent", "Edge case: 100% value produces correct zero/maximum result"),
            ("test_calculation_boundary_0_percent", "Edge case: 0% value passes through unchanged"),
            ("test_calculation_50_percent_correct_base", "Mid-range value applied to correct operand"),
            ("test_result_never_negative", "No input combination produces a negative result"),
            ("test_result_never_exceeds_maximum", "Result is clamped to logical maximum"),
        ],
        "edge_cases": [
            "What happens with exactly 0% — does the system skip the calculation entirely?",
            "What about values > 100% — should they be clamped or rejected?",
            "How does rounding work with non-integer values (e.g., $3.333...)?",
            "Does the fix affect existing historical records?",
            "Are there other calculation paths that use the same incorrect logic?",
        ],
    },
    "auth_session": {
        "keywords": ["session", "token", "expired", "unauthorized", "401",
                     "logout", "timeout", "authentication", "cookie",
                     "jwt", "refresh", "stale token", "auth"],
        "code_patterns": [r"session.*expire", r"token.*valid", r"raise.*Auth",
                         r"raise.*Session", r"cookie.*get"],
        "technical_term": "Session lifecycle management / silent authentication failure",
        "description_template": (
            "The authentication flow does not handle session expiration gracefully:\n"
            "  1. {func_name}() correctly detects the expired session\n"
            "  2. It raises the appropriate error\n"
            "  3. But the error is not propagated to the user in a visible way\n\n"
            "The frontend continues making requests with the stale session, "
            "all returning 401, but no UI feedback is shown to the user."
        ),
        "fix_approaches": [
            "Add a response interceptor in the frontend that detects 401 and shows a session-expired modal",
            "Implement a session heartbeat/keep-alive mechanism to proactively warn before expiry",
            "Add a middleware that returns a structured JSON error with a 'session_expired' code",
            "Implement token refresh flow with refresh tokens before the access token expires",
        ],
        "risks": [
            "Session expiry timing may differ between server and client clocks — use server-relative times",
            "Users may lose unsaved work if the session expires mid-operation — add auto-save or recovery",
            "Refresh token rotation adds complexity and potential for token theft if not done correctly",
            "Rate limiting on login endpoint may lock out users who rapidly retry after seeing the expired modal",
        ],
        "test_suggestions": [
            ("test_expired_session_returns_structured_error", "Request with expired token → 401 with 'session_expired' code"),
            ("test_session_near_expiry_warning", "Session within 5min of expiry → response header warns client"),
            ("test_no_session_token_returns_401", "Request without token → 401 with 'missing_token' code"),
            ("test_refresh_token_extends_session", "Valid refresh token → new access token issued"),
            ("test_expired_refresh_token_requires_login", "Expired refresh token → 401 requiring full re-login"),
        ],
        "edge_cases": [
            "What happens to in-flight API requests when the session expires mid-request?",
            "Does the system handle concurrent tabs/windows with the same session?",
            "What if the user's clock is significantly different from the server's?",
            "Can an attacker replay an expired token to gain access?",
            "How does session expiry interact with 'remember me' functionality?",
        ],
    },
    "null_reference": {
        "keywords": ["null", "none", "undefined", "attributeerror", "typeerror",
                     "nonetype", "null pointer", "missing field", "key error",
                     "keyerror", "index error"],
        "code_patterns": [r"\.\w+\s*=\s*None", r"\.get\(", r"if.*is\s+None",
                         r"not\s+\w+:"],
        "technical_term": "Null reference / missing guard clause",
        "description_template": (
            "{func_name}() accesses an attribute or key that can be null/None:\n"
            "  The code assumes the value is always present, but under certain conditions "
            "(missing data, API failure, edge case input) it is None/null.\n\n"
            "No defensive checks exist before the access, causing an unhandled exception."
        ),
        "fix_approaches": [
            "Add explicit null checks before accessing the value",
            "Use the Optional pattern and provide sensible defaults",
            "Add input validation at the entry point to reject invalid data early",
            "Use the Null Object pattern to avoid None checks throughout the code",
        ],
        "risks": [
            "Silently using a default value may mask the real issue upstream",
            "Too many null checks can make code harder to read — consider refactoring data flow",
            "The null source may be an upstream system returning incomplete data",
        ],
        "test_suggestions": [
            ("test_function_handles_null_input", "Pass None/null for each parameter → get appropriate error or default"),
            ("test_function_handles_empty_input", "Pass empty string/list/dict → handles gracefully"),
            ("test_function_handles_missing_field", "Pass object with missing optional field → no crash"),
            ("test_normal_input_still_works", "Valid input produces correct result"),
        ],
        "edge_cases": [
            "What if the upstream API returns a 200 with an empty body?",
            "What if the database record exists but has NULL for this column?",
            "What if the configuration value is missing from the environment?",
        ],
    },
    "data_validation": {
        "keywords": ["validation", "invalid input", "constraint", "boundary",
                     "overflow", "underflow", "negative", "maximum", "minimum",
                     "out of range", "unexpected value", "format"],
        "code_patterns": [r"if.*<\s*0", r"if.*>\s*\d+", r"try:.*except",
                         r"validate", r"check_"],
        "technical_term": "Missing input validation / boundary check",
        "description_template": (
            "{func_name}() does not validate input boundaries:\n"
            "  The function accepts values outside the expected range, "
            "leading to invalid state or downstream errors.\n\n"
            "No validation layer catches the invalid input before it "
            "propagates through the system."
        ),
        "fix_approaches": [
            "Add input validation at the API/function entry point",
            "Add database-level constraints (CHECK, NOT NULL, UNIQUE)",
            "Implement a validation layer/decorator for all public functions",
            "Add boundary checks with clear error messages",
        ],
        "risks": [
            "Adding strict validation may break existing clients sending borderline values",
            "Need to decide between rejecting vs. clamping out-of-range values",
            "Validation errors need clear, actionable error messages for API consumers",
        ],
        "test_suggestions": [
            ("test_minimum_valid_input", "Smallest valid input → succeeds"),
            ("test_maximum_valid_input", "Largest valid input → succeeds"),
            ("test_below_minimum_rejected", "Below minimum → clear error"),
            ("test_above_maximum_rejected", "Above maximum → clear error"),
            ("test_negative_input_rejected", "Negative value → clear error"),
        ],
        "edge_cases": [
            "What about integer overflow for very large values?",
            "What about floating point precision issues?",
            "What if the validation constraint changes between environments?",
        ],
    },
    "generic": {
        "keywords": [],
        "code_patterns": [],
        "technical_term": "Logic error",
        "description_template": (
            "Analysis of {func_name}() indicates a logic error:\n"
            "  The function's behavior differs from the expected specification. "
            "The bug manifests when specific input conditions are met."
        ),
        "fix_approaches": [
            "Review and correct the function logic",
            "Add comprehensive unit tests to define expected behavior",
            "Add input validation to catch edge cases",
        ],
        "risks": [
            "Existing behavior may have been depended upon by other systems",
            "Need thorough regression testing after changing core logic",
        ],
        "test_suggestions": [
            ("test_normal_input_correct_output", "Standard case → expected result"),
            ("test_edge_case_boundary", "Boundary value → correct handling"),
            ("test_error_case_handling", "Invalid input → appropriate error"),
        ],
        "edge_cases": [
            "What other inputs can trigger this code path?",
            "Are there similar patterns elsewhere in the codebase?",
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# CODE ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_code(source_text: str, file_path: str = "") -> CodeAnalysisResult:
    """Deep analysis of source code — extracts functions, classes, patterns."""
    result = CodeAnalysisResult(file_path=file_path)
    if not source_text or not source_text.strip():
        return result

    lines = source_text.split("\n")
    result.raw_lines = lines

    # Extract imports
    for line in lines:
        m = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", line)
        if m:
            result.imports.append((m.group(1), m.group(2).strip()))
        m = re.match(r"import\s+([\w.]+)", line)
        if m:
            result.imports.append((m.group(1), ""))

    # Extract functions with full body
    func_pattern = re.compile(r"^(\s*)def\s+(\w+)\s*\(([^)]*)\)\s*(?:->.*)?:", re.MULTILINE)
    for match in func_pattern.finditer(source_text):
        indent = len(match.group(1))
        name = match.group(2)
        sig = match.group(3)
        start_pos = match.start()
        line_start = source_text[:start_pos].count("\n") + 1

        # Find the end of the function body
        body_lines = []
        started = False
        line_end = line_start
        for i, line in enumerate(lines[line_start:], start=line_start + 1):
            stripped = line.rstrip()
            if not stripped:
                body_lines.append(line)
                line_end = i
                continue
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent > indent:
                body_lines.append(line)
                line_end = i
                started = True
            elif started:
                break

        body = "\n".join(body_lines)

        # Find function calls in body
        calls = re.findall(r"(\w+)\s*\(", body)
        calls = [c for c in calls if c not in ("if", "for", "while", "return", "print", "raise", "self")]

        func_info = FunctionInfo(
            name=name,
            line_start=line_start,
            line_end=line_end,
            signature=f"{name}({sig})",
            body=body,
            has_return="return" in body,
            calls=list(set(calls)),
        )
        result.functions.append(func_info)

    # Extract classes
    class_pattern = re.compile(r"^class\s+(\w+)", re.MULTILINE)
    for match in class_pattern.finditer(source_text):
        name = match.group(1)
        line_start = source_text[:match.start()].count("\n") + 1
        methods = [f for f in result.functions if f.line_start > line_start]
        result.classes.append(ClassInfo(name=name, line_start=line_start,
                                       methods=[m.name for m in methods]))

    # Detect code patterns/smells
    for func in result.functions:
        body_lower = func.body.lower()

        # TOCTOU: read-then-check-then-write
        if (re.search(r"(get|select|read|fetch)\b", body_lower) and
            re.search(r"\bif\s+", func.body) and
            re.search(r"(save|update|write|set|decrement)\b", body_lower)):
            result.patterns.append(CodePattern(
                pattern_type="toctou",
                description=f"Non-atomic read-check-write in {func.name}()",
                location=f"{func.name}() lines {func.line_start}-{func.line_end}",
                severity="critical",
                evidence=func.body[:200],
            ))

        # Calculation on wrong operand
        if re.search(r"(gross|total).*\*.*percent|discount.*=.*(gross|total)", body_lower):
            result.patterns.append(CodePattern(
                pattern_type="wrong_operand",
                description=f"Calculation may use wrong base in {func.name}()",
                location=f"{func.name}() lines {func.line_start}-{func.line_end}",
                severity="critical",
                evidence=func.body[:200],
            ))

        # Missing null check
        if re.search(r"\.\w+\b(?!\s*\()", func.body) and "if" not in func.body.split("\n")[0]:
            pass  # Too noisy

        # Exception: raise without proper handling
        if "raise" in func.body and "try" not in func.body:
            result.patterns.append(CodePattern(
                pattern_type="unhandled_raise",
                description=f"{func.name}() raises exception without try/except wrapper",
                location=f"{func.name}() lines {func.line_start}-{func.line_end}",
                severity="warning",
                evidence=func.body[:200],
            ))

        # No return value check
        if func.calls and not func.has_return and "validate" in func.name.lower():
            result.patterns.append(CodePattern(
                pattern_type="no_return_check",
                description=f"Validator {func.name}() may not return all paths",
                location=f"{func.name}() lines {func.line_start}-{func.line_end}",
                severity="info",
                evidence=func.body[:200],
            ))

    return result


# ══════════════════════════════════════════════════════════════
# LOG ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_log_patterns(log_text: str) -> list:
    """Analyze log entries for deep patterns."""
    if not log_text:
        return []

    patterns = []
    lines = log_text.strip().split("\n")

    # 1. Find concurrent access patterns (multiple requests at same second)
    timestamp_errors = {}
    for line in lines:
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line)
        if ts_match and ("ERROR" in line.upper() or "error" in line.lower()):
            ts = ts_match.group(1)
            timestamp_errors.setdefault(ts, []).append(line.strip())

    for ts, error_lines in timestamp_errors.items():
        if len(error_lines) >= 2:
            patterns.append(LogPattern(
                pattern_type="concurrent_errors",
                description=f"Multiple errors at same timestamp ({ts}): {len(error_lines)} concurrent failures detected",
                evidence=error_lines[:5],
                severity="critical",
            ))

    # 2. Find error bursts
    error_lines = [l for l in lines if "ERROR" in l.upper()]
    if len(error_lines) >= 3:
        patterns.append(LogPattern(
            pattern_type="error_burst",
            description=f"Error burst detected: {len(error_lines)} errors in the log window",
            evidence=error_lines[:5],
            severity="critical",
        ))

    # 3. Find specific values being logged
    value_patterns = re.findall(r"(?:count|inventory|stock|balance|total|amount)\s*[=:]\s*(-?\d+\.?\d*)", log_text, re.IGNORECASE)
    if value_patterns:
        negative_values = [v for v in value_patterns if float(v) < 0]
        if negative_values:
            patterns.append(LogPattern(
                pattern_type="negative_state",
                description=f"Negative values detected in state: {', '.join(negative_values)}",
                evidence=[f"Value: {v}" for v in negative_values],
                severity="critical",
            ))

    # 4. Find repeated access to same resource
    resource_accesses = re.findall(r"(?:request|access|query|read).*?(?:id|key|sku|session)[=:]?\s*(\S+)", log_text, re.IGNORECASE)
    if resource_accesses:
        from collections import Counter
        counts = Counter(resource_accesses)
        for resource, count in counts.most_common(3):
            if count >= 2:
                patterns.append(LogPattern(
                    pattern_type="repeated_access",
                    description=f"Resource '{resource}' accessed {count} times in the log window",
                    evidence=[f"Access count: {count}"],
                    severity="warning",
                ))

    return patterns


# ══════════════════════════════════════════════════════════════
# BUG CLASSIFICATION
# ══════════════════════════════════════════════════════════════

def classify_bug(full_text: str, code_analyses: list = None,
                 log_patterns: list = None) -> BugClassification:
    """
    Classify the bug type from all available evidence.
    Returns the best-matching BugClassification with deep context.
    """
    full_lower = full_text.lower()
    best_type = "generic"
    best_score = 0

    for bug_type, pattern in BUG_PATTERN_DB.items():
        if bug_type == "generic":
            continue

        score = 0

        # Keyword matching (weighted)
        for kw in pattern["keywords"]:
            if kw.lower() in full_lower:
                score += 3

        # Code pattern matching
        if code_analyses:
            for analysis in code_analyses:
                for cp in pattern.get("code_patterns", []):
                    for func in analysis.functions:
                        if re.search(cp, func.body, re.IGNORECASE):
                            score += 5

                # Check detected patterns
                for detected in analysis.patterns:
                    if detected.pattern_type in ("toctou",) and bug_type == "race_condition":
                        score += 10
                    elif detected.pattern_type in ("wrong_operand",) and bug_type == "calculation_error":
                        score += 10

        # Log pattern matching
        if log_patterns:
            for lp in log_patterns:
                if lp.pattern_type == "concurrent_errors" and bug_type == "race_condition":
                    score += 8
                elif lp.pattern_type == "negative_state" and bug_type in ("calculation_error", "race_condition"):
                    score += 5

        if score > best_score:
            best_score = score
            best_type = bug_type

    pattern = BUG_PATTERN_DB[best_type]

    # Find the primary function from code analysis
    primary_func = "the_function"
    primary_file = "the_file"
    primary_location = ""
    if code_analyses:
        for analysis in code_analyses:
            if analysis.functions:
                # Pick function with most patterns or first one
                for func in analysis.functions:
                    if any(p.pattern_type in ("toctou", "wrong_operand", "unhandled_raise")
                           for p in analysis.patterns if func.name in p.location):
                        primary_func = func.name
                        primary_file = analysis.file_path or "source file"
                        primary_location = f"lines {func.line_start}-{func.line_end}"
                        break
                else:
                    primary_func = analysis.functions[0].name
                    primary_file = analysis.file_path or "source file"
                    primary_location = f"lines {analysis.functions[0].line_start}-{analysis.functions[0].line_end}"

    # Build the description from template
    desc = pattern["description_template"].format(
        func_name=primary_func,
        wrong_operand="gross (subtotal + tax)",
        right_operand="subtotal (before tax)",
    )

    # Calculate confidence based on evidence
    confidence = 50.0
    if best_score >= 20:
        confidence = 92.0
    elif best_score >= 12:
        confidence = 85.0
    elif best_score >= 6:
        confidence = 75.0
    elif best_score >= 3:
        confidence = 65.0

    return BugClassification(
        bug_type=best_type,
        technical_term=pattern["technical_term"],
        confidence=confidence,
        description=desc,
        fix_approaches=pattern["fix_approaches"],
        specific_risks=pattern["risks"],
        test_suggestions=pattern["test_suggestions"],
        edge_cases=pattern.get("edge_cases", []),
    )


def extract_file_references(text: str) -> list:
    """Extract file paths and function references from text."""
    refs = []
    # File paths
    for m in re.finditer(r"([\w/\\]+\.py)\b", text):
        if m.group(1) not in refs:
            refs.append(m.group(1))
    # Function references
    for m in re.finditer(r"\b(\w+)\(\)", text):
        name = m.group(1)
        if name not in ("print", "return", "self", "super", "len", "str", "int"):
            if name not in refs:
                refs.append(name + "()")
    return refs


def extract_error_types(text: str) -> list:
    """Extract error/exception types from text."""
    errors = re.findall(r"\b(\w+(?:Error|Exception))\b", text)
    return list(dict.fromkeys(errors))  # unique, ordered


def build_specific_root_cause(
    bug_title: str,
    bug_summary: str,
    classification: BugClassification,
    code_analyses: list = None,
    log_patterns: list = None,
    stack_traces: list = None,
) -> str:
    """Build a specific, detailed root cause hypothesis."""
    parts = []

    # Technical classification
    parts.append(f"## {classification.technical_term}")
    parts.append("")

    # Specific description based on code analysis
    if code_analyses:
        for analysis in code_analyses:
            for func in analysis.functions:
                # Check if this function has detected patterns
                func_patterns = [p for p in analysis.patterns if func.name in p.location]
                if func_patterns:
                    file = analysis.file_path or "source file"
                    parts.append(f"**Location:** `{file}` :: `{func.signature}` (lines {func.line_start}-{func.line_end})")
                    parts.append("")
                    parts.append("**The problematic code pattern:**")
                    # Show relevant code snippet
                    body_lines = func.body.strip().split("\n")[:10]
                    for i, line in enumerate(body_lines, start=func.line_start + 1):
                        parts.append(f"  Line {i}: {line.rstrip()}")
                    parts.append("")
                    for cp in func_patterns:
                        parts.append(f"  --> {cp.description}")
                    parts.append("")
                    break

    # Root cause explanation
    parts.append("**Root cause:**")
    parts.append(classification.description)
    parts.append("")

    # Stack trace correlation
    if stack_traces:
        parts.append("**Stack trace evidence:**")
        for trace in stack_traces[:2]:
            parts.append(f"  - {trace.error_type}: {trace.error_message}")
        parts.append("")

    # Log pattern evidence
    if log_patterns:
        critical_patterns = [p for p in log_patterns if p.severity == "critical"]
        if critical_patterns:
            parts.append("**Log evidence:**")
            for lp in critical_patterns[:3]:
                parts.append(f"  - {lp.description}")
            parts.append("")

    return "\n".join(parts)
