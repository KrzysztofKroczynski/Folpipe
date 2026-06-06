import json
import os
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs"


def self_knowledge(topic: str) -> dict:
    if not _DOCS_DIR.exists():
        return {"error": "docs/ directory not found."}
    topics = {p.stem: p for p in sorted(_DOCS_DIR.glob("*.md"))}
    if not topic:
        return {"topics": list(topics.keys())}
    if topic in topics:
        return {"content": topics[topic].read_text(encoding="utf-8")}
    close = [t for t in topics if topic in t or t in topic]
    msg = f"Unknown topic: {topic!r}."
    if close:
        msg += f" Did you mean: {', '.join(close)}?"
    else:
        msg += f" Available: {', '.join(topics)}."
    return {"error": msg}


class PipelineCancelledError(Exception):
    """Raised when the model calls cancel_pipeline. Carries the mandatory reason."""
    def __init__(self, reason: str, step_id: str = ""):
        self.reason = reason
        self.step_id = step_id
        super().__init__(reason)


class Sandbox:
    """
    Filesystem sandbox for pipeline step execution.

    Containment is checked on the *lexical* (pre-symlink) path so that symlinks
    placed inside the pipeline directory act as user-granted shortcuts to external
    resources — the symlink itself lives inside the boundary, which is sufficient
    authorization.

    Files matching secret patterns (.env, *.key, etc.) are always blocked regardless
    of location.

    run_script working_dir must be inside pipeline_path (lexically).
    """

    _BLOCKED_PATTERNS = (
        ".env", "*.env", ".env.*",
        "secrets.*", "*.secret",
        "*.key", "*.pem", "*.p12", "*.pfx", "*.crt",
    )

    def __init__(self, pipeline_path: Path):
        self.pipeline_path = pipeline_path.resolve()

    def _lexical(self, path: Path) -> Path:
        """Normalize path without following symlinks (collapse .., make absolute)."""
        return Path(os.path.normpath(os.path.abspath(path)))

    def _is_blocked_name(self, path: Path) -> bool:
        return any(fnmatch(path.name, pat) for pat in self._BLOCKED_PATTERNS)

    def check_read(self, path: Path) -> tuple[bool, str]:
        """Return (allowed, denial_reason)."""
        # Block secret-named files no matter where they live
        if self._is_blocked_name(path):
            return False, f"Access denied: '{path.name}' is a protected file"

        # Lexical containment check — symlinks inside the pipeline dir are allowed shortcuts
        lexical = self._lexical(path)
        try:
            lexical.relative_to(self.pipeline_path)
            return True, ""
        except ValueError:
            return False, "Access denied: path is outside the pipeline directory"

    def check_script_dir(self, path: Path) -> tuple[bool, str]:
        """Return (allowed, denial_reason). working_dir must be within pipeline_path (lexically)."""
        lexical = self._lexical(path)
        try:
            lexical.relative_to(self.pipeline_path)
            return True, ""
        except ValueError:
            return False, "Access denied: working_dir must be within the pipeline directory"


BUILTIN_SCHEMAS = [
    {
        "name": "read_file",
        "description": (
            "Read a file by path. Use to load documents, configs, or any file content. "
            "Supports optional line range for large files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (absolute or relative to pipeline dir)"},
                "start_line": {"type": "integer", "description": "Start line (1-indexed, optional)"},
                "end_line": {"type": "integer", "description": "End line inclusive (optional)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write or append content to a file inside your step's output folder. "
            "Relative paths are resolved under output/<step_id>/. "
            "Absolute paths must also be within that folder. "
            "Creates parent directories as needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative to step output folder, or absolute within it)"},
                "content": {"type": "string", "description": "Content to write"},
                "mode": {
                    "type": "string",
                    "enum": ["write", "append"],
                    "description": "write (overwrite, default) or append",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "write_state",
        "description": (
            "Save a value to the pipeline's shared state so the next step can read it. "
            "Call this before finishing your step."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "State key"},
                "value": {"description": "Value — string, number, list, or object"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web. Returns titles, URLs, and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Results to return (default 5, max 20)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "http_request",
        "description": "Make an HTTP request. Use for APIs, webhooks, or fetching URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                "url": {"type": "string"},
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"description": "Request body (string or object)"},
                "timeout": {"type": "integer", "description": "Timeout seconds (default 30)"},
            },
            "required": ["method", "url"],
        },
    },
    {
        "name": "run_script",
        "description": "Execute a shell command. Use for CLI tools and scripts. Use with care.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
                "working_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout seconds (default 60)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "extract_json",
        "description": "Parse a JSON string and optionally query it with a dot-path expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "JSON string to parse"},
                "path": {"type": "string", "description": "Dot-path query e.g. 'results.0.name' (optional)"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "template",
        "description": "Render a Jinja2 template with given variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "Jinja2 template string"},
                "variables": {"type": "object", "description": "Variables to inject"},
            },
            "required": ["template", "variables"],
        },
    },
    {
        "name": "dispatch_task",
        "description": (
            "Spawn an ad-hoc sub-task. Call multiple times in one response to run tasks in "
            "parallel — the runner detects the batch and executes them concurrently. "
            "Use 'substep' to run a named sub-step from the current step's folder, which loads "
            "its own SKILL.md and tools. Use 'skill' for inline one-off instructions instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What the sub-task should do"},
                "substep": {
                    "type": "string",
                    "description": (
                        "Name of a sub-step folder inside the current step (e.g. 'sub-01-chunk'). "
                        "Loads that sub-step's SKILL.md and tools. Takes priority over 'skill'."
                    ),
                },
                "skill": {"type": "string", "description": "Inline instructions for the sub-task (used when no substep)"},
                "name": {"type": "string", "description": "Short descriptive name for this ad-hoc agent (e.g. 'search-llm-basics'). Used as its output directory name. Required for inline skill tasks."},
                "context": {"type": "object", "description": "Extra context to pass to the sub-task"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "cancel_pipeline",
        "description": (
            "Immediately stop the pipeline run. Use when continuing would produce meaningless output — "
            "e.g. the job is a complete mismatch, required input is missing, or the user explicitly quit. "
            "A reason is required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the pipeline is being cancelled. Will be written to output/cancelled.md."},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "ask_human",
        "description": (
            "Pause and collect a human response via the console. "
            "Use only when a decision genuinely requires human judgment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question to show the human"},
                "context": {"type": "string", "description": "Additional context (optional)"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "self_knowledge",
        "description": (
            "Read folpipe documentation. Use to look up framework features, "
            "configuration options, and best practices. Omit 'topic' to list all topics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Documentation topic (e.g. 'tools', 'pipeline-structure', "
                        "'context-management', 'execution-patterns', 'state', 'cli'). "
                        "Omit to list all available topics."
                    ),
                }
            },
            "required": [],
        },
    },
]

BUILTIN_NAMES = {s["name"] for s in BUILTIN_SCHEMAS}


class BuiltinExecutor:
    def __init__(self, state, pipeline_path: Path, step_id: str, model_config: dict, logger, sandbox: Sandbox | None = None):
        self.state = state
        self.pipeline_path = Path(pipeline_path)
        self.step_id = step_id
        self.model_config = model_config
        self.logger = logger
        self.sandbox = sandbox or Sandbox(self.pipeline_path)

    @property
    def output_path(self) -> Path:
        return self.pipeline_path / "output" / self.step_id if self.step_id else self.pipeline_path / "output"

    def execute(self, name: str, args: dict) -> Any:
        handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "write_state": self._write_state,
            "web_search": self._web_search,
            "http_request": self._http_request,
            "run_script": self._run_script,
            "extract_json": self._extract_json,
            "template": self._template,
            "cancel_pipeline": self._cancel_pipeline,
            "ask_human": self._ask_human,
            "self_knowledge": self._self_knowledge,
        }
        fn = handlers.get(name)
        if fn is None:
            return {"error": f"Unknown builtin: {name}"}
        try:
            return fn(args)
        except PipelineCancelledError:
            raise
        except Exception as e:
            return {"error": str(e)}

    def _read_file(self, args: dict) -> dict:
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.pipeline_path / path
        allowed, reason = self.sandbox.check_read(path)
        if not allowed:
            return {"error": reason}
        if not path.exists():
            return {"error": f"File not found: {path}"}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, args.get("start_line", 1) - 1)
        end = args.get("end_line", len(lines))
        selected = lines[start:end]
        return {"content": "\n".join(selected), "lines": len(selected), "path": str(path)}

    def _write_file(self, args: dict) -> dict:
        path = Path(args["path"])
        output_path = self.output_path
        if not path.is_absolute():
            path = output_path / path
        try:
            path.resolve().relative_to(output_path.resolve())
        except ValueError:
            return {"error": f"Write denied: path must be within {output_path}"}
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.get("mode") == "append" else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(args["content"])
        return {"ok": True, "path": str(path)}

    def _write_state(self, args: dict) -> dict:
        self.state.set(args["key"], args["value"])
        return {"ok": True, "key": args["key"]}

    def _web_search(self, args: dict) -> dict:
        import httpx
        query = args["query"]
        num = min(args.get("num_results", 5), 20)
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1"},
            timeout=15,
        )
        data = resp.json()
        results = []
        for topic in data.get("RelatedTopics", [])[:num]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("Text", "")[:120],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })
        if not results and data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
            })
        return {"results": results, "query": query}

    def _http_request(self, args: dict) -> dict:
        import httpx
        method = args["method"].upper()
        url = args["url"]
        headers = args.get("headers", {})
        body = args.get("body")
        timeout = args.get("timeout", 30)
        if isinstance(body, dict):
            resp = httpx.request(method, url, headers=headers, json=body, timeout=timeout)
        else:
            resp = httpx.request(method, url, headers=headers, content=body, timeout=timeout)
        try:
            return {"status": resp.status_code, "body": resp.json(), "headers": dict(resp.headers)}
        except Exception:
            return {"status": resp.status_code, "body": resp.text, "headers": dict(resp.headers)}

    def _run_script(self, args: dict) -> dict:
        cwd_raw = args.get("working_dir", str(self.pipeline_path))
        allowed, reason = self.sandbox.check_script_dir(Path(cwd_raw))
        if not allowed:
            return {"error": reason}
        timeout = args.get("timeout", 60)
        result = subprocess.run(
            args["command"],
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd_raw,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "ok": result.returncode == 0,
        }

    def _extract_json(self, args: dict) -> dict:
        data = json.loads(args["content"])
        path = args.get("path")
        if not path:
            return {"result": data}
        # Dot-path traversal
        current = data
        for part in path.split("."):
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return {"error": f"Index '{part}' out of range"}
            elif isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return {"result": None}
            else:
                return {"error": f"Cannot traverse into {type(current).__name__}"}
        return {"result": current}

    def _template(self, args: dict) -> dict:
        from jinja2 import Template
        rendered = Template(args["template"]).render(**args.get("variables", {}))
        return {"result": rendered}

    def _cancel_pipeline(self, args: dict) -> dict:
        raise PipelineCancelledError(reason=args["reason"], step_id=self.step_id)

    def _ask_human(self, args: dict) -> dict:
        print("\n" + "=" * 60)
        print("HUMAN INPUT REQUIRED")
        if args.get("context"):
            print(f"\nContext:\n{args['context']}\n")
        print(f"Question: {args['question']}")
        print("-" * 60)
        try:
            response = input("Your response: ").strip()
            return {"response": response}
        except (EOFError, KeyboardInterrupt):
            return {"error": "No human input available"}

    def _self_knowledge(self, args: dict) -> dict:
        return self_knowledge(args.get("topic", ""))
