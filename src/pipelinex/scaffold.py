from pathlib import Path

_PIPELINE_YAML = """\
name: {name}
version: 1.0.0

# Model — swap provider/name to switch. Any LiteLLM-supported provider works.
# DeepSeek is a cost-effective default with strong tool-calling support.
model:
  provider: deepseek
  name: deepseek-chat
  api_key: ${{DEEPSEEK_API_KEY}}

# --- other providers (uncomment one to use) ---

# Anthropic
# model:
#   provider: anthropic
#   name: claude-sonnet-4-6
#   api_key: ${{ANTHROPIC_API_KEY}}

# OpenAI
# model:
#   provider: openai
#   name: gpt-4o
#   api_key: ${{OPENAI_API_KEY}}

# Google Gemini
# model:
#   provider: google
#   name: gemini-2.0-flash
#   api_key: ${{GEMINI_API_KEY}}

# Groq  (fast inference, free tier available)
# model:
#   provider: groq
#   name: llama-3.3-70b-versatile
#   api_key: ${{GROQ_API_KEY}}

# Mistral
# model:
#   provider: mistral
#   name: mistral-large-latest
#   api_key: ${{MISTRAL_API_KEY}}

# Ollama  (local, no key needed)
# model:
#   provider: ollama
#   name: llama3.1

# Any OpenAI-compatible endpoint
# model:
#   provider: openai
#   name: my-model
#   base_url: https://my-endpoint.com/v1
#   api_key: ${{MY_API_KEY}}

# self_reflection: true   # opt-in: after each step the model rewrites its own SKILL.md with lessons learned

steps:
  - id: step-01-ingest

  - id: step-02-process
    max_iterations: 100
    can_goto:
      - step-02-process
      - step-03-output

  - id: step-03-output
    terminal: true
"""

_GLOBAL_SKILL = """\
---
name: {name}
description: Describe what this pipeline does in one sentence.
---

# {name}

Describe what this pipeline does in one or two sentences.

## Purpose

Who uses this pipeline and what problem it solves.

## Rules

- List any rules that apply to every step (tone, output format, citation requirements, etc.)
- "Never invent data — if something is missing, say so and stop."
- Keep each step's output focused; don't duplicate work from previous steps.

## Tools available

The built-in tools (read_file, write_file, write_state, web_search, http_request,
run_script, extract_json, template, dispatch_task, ask_human, cancel_pipeline, self_knowledge)
are always available. List any pipeline-level custom tools here so every step knows about them.
"""

_STEP_SKILL = """\
---
name: {step_id}
description: One sentence describing what this step does.
---

# {step_id}

One sentence describing what this step does and why it exists.

## Context

Describe which state keys this step needs. Be explicit — name the key and signal its importance.

"handoff" from the previous step is essential — read it before doing anything.
"documents" is essential — you'll process every entry.
"config" is useful — it sets parameters for this step.
"raw_responses" and "debug_log" are not needed, skip them.

## Task

Describe what to do — written as you'd explain it to a smart colleague.
Mention which tools to use and in what order.

Before finishing, leave a brief handoff note:
write_state(key="handoff", value="<one sentence: what was done and what the next step should know>")

## When things go wrong

- If a tool call fails once, retry with a corrected argument.
- If it fails twice, note the failure in state and continue with the remaining work.
- If the step cannot proceed at all, stop and write a clear error to state before exiting.

## Notes

Edge cases, known gotchas, or examples worth preserving here.
"""

_TOOL_JSON = """\
{{
  "name": "{name}",
  "description": "Describe when to use this tool and when NOT to.",
  "inputSchema": {{
    "type": "object",
    "properties": {{
      "input": {{
        "type": "string",
        "description": "Input value"
      }}
    }},
    "required": ["input"]
  }},
  "run": "run.py",
  "deps": []
}}
"""

_TOOL_RUN = """\
import sys
import json

args = json.load(sys.stdin)

# TODO: implement tool logic
result = {"ok": True, "output": f"Processed: {args.get('input', '')}"}

print(json.dumps(result))
"""

_ENV = """\
# Never commit this file — it contains secrets.

# Uncomment the key for whichever provider you configured in pipeline.yaml:
DEEPSEEK_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here
# GEMINI_API_KEY=your-key-here
# GROQ_API_KEY=your-key-here
# MISTRAL_API_KEY=your-key-here
"""

_GITIGNORE = """\
.env
output/
__pycache__/
*.pyc
*.pyo
"""


def scaffold_pipeline(name: str, base_dir: Path = Path(".")):
    d = Path(base_dir) / name
    d.mkdir(parents=True, exist_ok=True)

    (d / "pipeline.yaml").write_text(_PIPELINE_YAML.format(name=name), encoding="utf-8")
    (d / "SKILL.md").write_text(_GLOBAL_SKILL.format(name=name), encoding="utf-8")
    (d / ".env").write_text(_ENV, encoding="utf-8")
    (d / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")

    for sub in ("input", "output", "tools"):
        (d / sub).mkdir(exist_ok=True)

    for step_id in ("step-01-ingest", "step-02-process", "step-03-output"):
        scaffold_step(step_id, d, _quiet=True)

    print(f"Created pipeline: {d}")
    print(f"Next steps:")
    print(f"  1. Edit {d}/.env — add your API key")
    print(f"  2. Edit {d}/pipeline.yaml — configure steps and model")
    print(f"  3. Edit {d}/*/SKILL.md — write step instructions")
    print(f"  4. Drop files into {d}/input/")
    print(f"  5. Run: folpipe run {d}")
    print(f"")
    print(f"Docs: https://github.com/kroczynskikrzysztof/pipelinex/tree/main/docs")


def scaffold_step(step_id: str, pipeline_dir: Path, _quiet: bool = False):
    d = Path(pipeline_dir) / step_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(_STEP_SKILL.format(step_id=step_id), encoding="utf-8")
    (d / "tools").mkdir(exist_ok=True)
    if not _quiet:
        print(f"Created step: {d}")
        print(f"  Edit {d}/SKILL.md to write the step instructions")


def scaffold_tool(name: str, tools_dir: Path):
    d = Path(tools_dir) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "tool.json").write_text(_TOOL_JSON.format(name=name), encoding="utf-8")
    (d / "run.py").write_text(_TOOL_RUN, encoding="utf-8")
    (d / "README.md").write_text(f"# {name}\n\nDescribe this tool.\n", encoding="utf-8")
    print(f"Created tool: {d}")
    print(f"  Edit {d}/tool.json — description and schema")
    print(f"  Edit {d}/run.py — tool implementation")
