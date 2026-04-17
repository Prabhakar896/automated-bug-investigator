"""
Repo Navigator Agent (Bonus) — maps the codebase, identifies relevant
modules and dependency chains related to the bug.

MCP integrations:
  - GitHub: search_code, get_file_contents
"""

import os
from pathlib import Path

from config import Config
from models.agent_outputs import FileInfo, RepoNavigatorOutput
from agents.base_agent import BaseAgent
from mcp.github_mcp import GitHubMCPClient
from utils.llm_client import get_llm_client


class RepoNavigatorAgent(BaseAgent):
    name = "repo_navigator_agent"
    description = "Map codebase structure, identify relevant modules and call chains"

    def __init__(self):
        super().__init__()
        self.github = GitHubMCPClient(demo_mode=Config.MCP_DEMO_MODE)

    def execute(self, input_data: dict, context: dict) -> RepoNavigatorOutput:
        """
        Scan the source directory and map relevant files.
        
        Args:
            input_data: dict with 'src_dir' path
            context: Pipeline context with triage output
        """
        src_dir = input_data.get("src_dir", str(Config.SRC_DIR))
        triage = context.get("triage_output")

        # Step 1: Scan the local source directory
        module_map = self._scan_directory(src_dir)
        self.log_tool_call("scan_directory", f"scanned {src_dir}")

        # Step 2: Search GitHub for relevant code related to the bug
        search_queries = ["discount", "calculate_order_total", "process_payment"]
        github_matches = {}
        
        for query in search_queries:
            self.log_tool_call("github.search_code", f"query='{query}'")
            result = self.github.search_code(query)
            for item in result.get("items", []):
                path = item.get("path", "")
                if path not in github_matches:
                    github_matches[path] = {
                        "matched_queries": [],
                        "score": item.get("score", 0),
                    }
                github_matches[path]["matched_queries"].append(query)

        # Step 3: Build relevance-ranked file list
        relevant_files = self._rank_files(module_map, github_matches, triage)

        # Step 4: Read key source files for context
        source_snippets = self._read_source_files(src_dir, relevant_files)
        self.log_tool_call("read_source_files", f"read {len(source_snippets)} files")

        # Step 5: Build dependency chain
        dependency_chain = self._trace_dependency_chain(source_snippets)

        return RepoNavigatorOutput(
            module_map=module_map,
            relevant_files=relevant_files,
            dependency_chain=dependency_chain,
            source_snippets=source_snippets,
        )

    def _scan_directory(self, src_dir: str) -> dict:
        """Scan source directory and build a module map."""
        module_map = {}
        src_path = Path(src_dir)

        if not src_path.exists():
            self.logger.warning(f"Source directory not found: {src_dir}")
            return module_map

        for py_file in src_path.rglob("*.py"):
            rel_path = str(py_file.relative_to(src_path.parent))
            # Read first few lines to get module docstring
            try:
                content = py_file.read_text(encoding="utf-8")
                first_lines = content.split("\n")[:5]
                docstring = ""
                for line in first_lines:
                    line = line.strip().strip('"').strip("'")
                    if line and not line.startswith("#") and not line.startswith("import"):
                        docstring = line
                        break
                module_map[rel_path] = docstring or "No description"
            except Exception as e:
                module_map[rel_path] = f"Error reading: {e}"

        return module_map

    def _rank_files(
        self, module_map: dict, github_matches: dict, triage
    ) -> list[FileInfo]:
        """Rank files by relevance to the bug."""
        files = []
        
        # Keywords that indicate relevance
        bug_keywords = ["payment", "discount", "order", "total", "calculate"]
        
        for path, desc in module_map.items():
            relevance = "low"
            key_functions = []
            
            # Check if file was mentioned in triage
            if triage:
                for comp in getattr(triage, "affected_components", []):
                    if path.replace("\\", "/") in comp.replace("\\", "/"):
                        relevance = "high"

            # Check GitHub search matches
            for gh_path, match_info in github_matches.items():
                if gh_path in path or path in gh_path:
                    if len(match_info["matched_queries"]) >= 2:
                        relevance = "high"
                    elif relevance != "high":
                        relevance = "medium"
                    key_functions.extend(match_info["matched_queries"])

            # Check keywords in path/description
            path_lower = path.lower()
            if any(kw in path_lower for kw in bug_keywords):
                if relevance == "low":
                    relevance = "medium"

            files.append(FileInfo(
                path=path,
                description=desc,
                relevance=relevance,
                key_functions=list(set(key_functions)),
            ))

        # Sort by relevance
        order = {"high": 0, "medium": 1, "low": 2}
        files.sort(key=lambda f: order.get(f.relevance, 3))

        return files

    def _read_source_files(self, src_dir: str, files: list[FileInfo]) -> dict:
        """Read contents of high/medium relevance files."""
        snippets = {}
        src_path = Path(src_dir)

        for file_info in files:
            if file_info.relevance in ("high", "medium"):
                # Try to read the file locally
                file_path = src_path.parent / file_info.path
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        snippets[file_info.path] = content
                    except Exception as e:
                        snippets[file_info.path] = f"Error reading: {e}"
                else:
                    # Fall back to GitHub MCP
                    self.log_tool_call("github.get_file_contents", file_info.path)
                    result = self.github.get_file_contents(file_info.path)
                    snippets[file_info.path] = result.get("content", "")

        return snippets

    def _trace_dependency_chain(self, source_snippets: dict) -> list[str]:
        """Trace the call chain dynamically from source code imports & function calls."""
        import re

        if not source_snippets:
            return ["No source files available to trace dependencies"]

        chain = []
        # Build a map of which files import/call which
        for path, content in source_snippets.items():
            if not content or content.startswith("Error"):
                continue
            
            # Find imports
            imports = re.findall(r'from\s+([\w.]+)\s+import\s+(.+)', content)
            for mod, names in imports:
                chain.append(f"{path} imports from {mod}: {names.strip()}")
            
            # Find function definitions
            funcs = re.findall(r'def\s+(\w+)\s*\(', content)
            if funcs:
                chain.append(f"{path} defines: {', '.join(funcs[:8])}")
            
            # Find class definitions
            classes = re.findall(r'class\s+(\w+)', content)
            if classes:
                chain.append(f"{path} classes: {', '.join(classes[:5])}")

        if not chain:
            chain = ["Dependency analysis: no imports or functions found in source files"]

        return chain

    def get_fallback_output(self, error: str) -> RepoNavigatorOutput:
        return RepoNavigatorOutput(
            module_map={"error": f"Repo navigation failed: {error}"},
        )
