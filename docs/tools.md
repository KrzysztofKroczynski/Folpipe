# Tools

## Built-in tools

Ship with the runner. Always available, no setup needed.

### read_file

Read a file by path. Supports optional line ranges for large files.

```
read_file(path="input/report.txt")
read_file(path="output/step-01/result.json", start_line=10, end_line=50)
```

Relative paths resolve from the pipeline directory.

**Sandbox:** paths outside the pipeline directory are denied. Secret-named files (`.env`, `*.key`, `*.pem`, etc.) are always blocked regardless of location. See [Filesystem Sandbox](sandbox.md).

---

### write_file

Write or append content to a file. Creates parent directories automatically.

```
write_file(path="summary.md", content="# Summary\n...")
write_file(path="log.txt", content="entry\n", mode="append")
```

Relative paths resolve to the current step's output folder (`output/<step_id>/`). Absolute paths must also be within that folder — writes outside it are rejected. The model should use short relative paths; the runner places them in the right location.

| Parameter | Required | Description |
|---|---|---|
| `path` | yes | File path (relative to `output/<step_id>/`, or absolute within it) |
| `content` | yes | Content to write |
| `mode` | no | `write` (default, overwrites) or `append` |

---

### write_state

Save a value to pipeline state so the next step can read it.

```
write_state(key="summary", value="done")
write_state(key="results", value=[{"file": "a.txt", "chunks": 3}])
```

Always call this before finishing a step. See [State & Handoffs](state.md).

---

### web_search

Search the web. Returns titles, URLs, and snippets via DuckDuckGo.

```
web_search(query="pipelinex agentic framework")
web_search(query="FastAPI vs Django 2025", num_results=10)
```

---

### http_request

Make any HTTP request. Use for APIs, webhooks, or fetching URLs.

```
http_request(method="GET", url="https://api.example.com/data")
http_request(
  method="POST",
  url="https://api.example.com/submit",
  headers={"Authorization": "Bearer token"},
  body={"key": "value"}
)
```

---

### run_script

Execute a shell command. Use for CLI tools, file operations, or anything not covered by other tools.

```
run_script(command="ls -la input/")
run_script(command="python convert.py input.csv", working_dir="scripts/", timeout=120)
```

**Sandbox:** `working_dir` must be inside the pipeline directory. Default timeout is 60 seconds; pass `timeout` to override.

---

### extract_json

Parse a JSON string and optionally query it with a dot-path expression.

```
extract_json(content='{"results": [{"name": "Alice"}]}')
extract_json(content=json_string, path="results.0.name")
```

---

### template

Render a Jinja2 template with given variables.

```
template(
  template="Hello {{ name }}, you have {{ count }} messages.",
  variables={"name": "Alice", "count": 5}
)
```

---

### dispatch_task

Spawn an ad-hoc sub-task. See [Execution Patterns](execution-patterns.md#parallel-dispatch) for full details.

```
dispatch_task(task="Summarise this document", skill="Be concise. Return plain text.", name="summarise-doc")
dispatch_task(task="Chunk intro-to-ml.txt", substep="sub-01-chunk", context={"filename": "intro-to-ml.txt", "content": "..."})
```

| Parameter | Required | Description |
|---|---|---|
| `task` | yes | What the sub-task should do |
| `substep` | no | Name of a sub-step folder inside the current step (loads its SKILL.md and tools) |
| `skill` | no | Inline instructions for the sub-task (used when no `substep`) |
| `name` | no | Short descriptive name for the ad-hoc agent (e.g. `"search-llm-basics"`). Used as its output directory name. Recommended for inline skill tasks. |
| `context` | no | Extra data to pass to the sub-task |

---

### cancel_pipeline

Immediately stop the pipeline run. The runner writes the reason to `output/cancelled.md` with a state snapshot.

```
cancel_pipeline(reason="Job description is in a language not supported by this pipeline.")
```

Use when continuing would produce meaningless output — e.g. required input is missing, the job is a complete mismatch, or a fatal error makes further steps pointless. Not for recoverable errors; use `When things go wrong` guidance in SKILL.md for those.

---

### ask_human

Pause and collect a human response via the console.

```
ask_human(question="Should we proceed with the redacted version?")
ask_human(question="Which output format?", context="Options: PDF, HTML, Markdown")
```

---

### self_knowledge

Read folpipe framework documentation. Use to look up available tools, pipeline configuration, execution patterns, and best practices.

```
self_knowledge()                          # list all available topics
self_knowledge(topic="tools")             # read the tools reference
self_knowledge(topic="execution-patterns")
self_knowledge(topic="context-management")
```

Available topics: `tools`, `pipeline-structure`, `state`, `execution-patterns`, `context-management`, `human-input`, `cli`, `getting-started`, `examples`.

---

## Custom tools

Drop a folder into `tools/` (pipeline-level) or `step-id/tools/` (step-local).

```
tools/
└── send_slack/
    ├── tool.json    # schema
    ├── run.py       # or run.sh / run.js
    └── README.md    # optional, for humans
```

### tool.json

MCP-compatible schema. The `description` is what the model reads to decide when to use the tool — write it for the model:

```json
{
  "name": "send_slack",
  "description": "Post a message to a Slack channel. Use when the pipeline needs a human in the loop — approvals, important failures, or results requiring a decision. Not for routine logging; use write_file for that.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "channel": {
        "type": "string",
        "description": "Slack channel name, e.g. #alerts"
      },
      "message": {
        "type": "string",
        "description": "Message text. Markdown supported."
      }
    },
    "required": ["channel", "message"]
  },
  "run": "run.py",
  "deps": ["slack-sdk"]
}
```

**`deps`** — Python packages required by the tool. The runner installs them automatically to `~/.pipelinex/envs/default` before the first run. No manual `pip install` needed.

### run.py

Receives args as JSON on stdin. Writes result as JSON to stdout. Exits non-zero on failure.

```python
import sys, json, os
from slack_sdk import WebClient

args = json.load(sys.stdin)
client = WebClient(token=os.environ["SLACK_TOKEN"])
client.chat_postMessage(channel=args["channel"], text=args["message"])
print(json.dumps({"ok": True}))
```

On failure, exit non-zero and include an `error` field:

```python
print(json.dumps({"error": "Slack API returned 403 — check SLACK_TOKEN"}))
sys.exit(1)
```

Any language works — runner detects `run.py`, `run.sh`, or `run.js` and executes the right interpreter.

### run.sh

```bash
#!/bin/bash
INPUT=$(cat)
CHANNEL=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['channel'])")
echo '{"ok": true}'
```

---

## Tool resolution order

Most specific wins:

```
sub-step tools/        →  step-02/sub-01-chunk/tools/
step-local tools/      →  step-02/tools/
pipeline-level tools/  →  tools/
global cache           →  ~/.pipelinex/tools/
built-in               →  (ships with runner)
```

Drop the same tool name at a more specific level to override it for that step or sub-step.

---

## Global tool cache

Tools shared across all pipelines on the machine live in:

```
~/.pipelinex/tools/
```

Drop a tool folder there once — every pipeline can use it.

---

## Dependency installation

On every `folpipe run`, the runner scans all tool `tool.json` files and installs any listed `deps` to `~/.pipelinex/envs/default`. This is a no-op if deps are already installed.

To install deps without running:

```bash
folpipe tools install ./my-pipeline
```
