# Execution Patterns

## Pattern 1 — Linear

Steps run in order. No extra config needed.

```yaml
steps:
  - id: step-01-ingest
  - id: step-02-process
  - id: step-03-output
    terminal: true
```

```
step-01 → step-02 → step-03
```

---

## Pattern 2 — Agent branching

The model decides which step comes next. Declare the valid targets in `can_goto`.

```yaml
steps:
  - id: step-03-validate
    can_goto:
      - step-04-output
      - step-05-partial-output
```

The model must include a routing JSON block in its final response:

```json
{"next": "step-04-output", "reason": "validation passed, all 47 chunks indexed"}
```

The runner validates `next` is in the `can_goto` whitelist. If the model omits it, the runner prompts once more then fails with an error report.

**SKILL.md guidance:**

```markdown
## Task
...do validation work...

When done, route to step-04-output if everything passed, or to
step-05-partial-output if more than a fifth of documents failed.
```

---

## Pattern 3 — Loop

A step routes back to itself via `can_goto`. Use for work that spans multiple passes.

```yaml
- id: step-02-process
  max_iterations: 500   # safety ceiling — stop if model loops unexpectedly
  can_goto:
    - step-02-process   # self-reference = can loop
    - step-03-validate
```

The model loops naturally when the SKILL.md describes iterative work:

```markdown
## Task

You have a list of documents to process. Work through each one.
Send documents for chunking in parallel. When all are done, move
to validation and leave a handoff summarising what succeeded and what didn't.
```

Each loop iteration starts fresh — the model only sees the current state and the handoff note from the previous pass, not the full conversation history. State accumulates across passes (this is intentional — it's how progress is tracked).

`max_iterations` is a safety ceiling, not a loop counter. The model decides when it's done.

---

## Pattern 4 — Parallel dispatch

The model discovers work at runtime and dispatches independent tasks concurrently.

**Single task:**
```
model calls dispatch_task(...)
runner executes it, returns result as tool response
model continues
```

**Parallel batch:**
```
model calls dispatch_task × N in a single response
runner detects the batch and spawns all concurrently
runner awaits all (with timeout), returns array of results
model receives all results and continues
```

The model parallelises in plain English:

```markdown
## Task

Process all documents at once — send them all for chunking in the
same breath rather than one at a time. You'll get all the results back together.
```

The model fires multiple `dispatch_task` calls in one response. The runner recognises the batch automatically. No special syntax needed.

### Inline dispatch

Pass instructions directly as `skill`:

```
dispatch_task(
  task="Summarise the introduction section",
  skill="Return a 2-sentence summary. No bullet points.",
  context={"text": "..."}
)
```

### Sub-step dispatch

Reference a named sub-step folder. The runner loads its `SKILL.md` (merged with parent SKILL.md) and its tools, then runs it with full tool access:

```
dispatch_task(
  task="Chunk intro-to-ml.txt into 500-word pieces",
  substep="sub-01-chunk",
  context={"filename": "intro-to-ml.txt", "content": "..."}
)
```

The sub-step lives at `step-02-process/sub-01-chunk/SKILL.md`. Sub-steps can also dispatch further tasks (up to `max_depth`).

### Failure in a parallel batch

The runner packages every failure alongside successes and returns the whole picture. The model reads its "When things go wrong" section and decides what to do. The runner doesn't decide — it just reports.

```markdown
## When things go wrong

If a chunk task fails: note it in the processed list with status "failed"
and continue. Don't let one bad document block the others.

If more than a third fail: route to step-05-partial-output instead of
step-03-validate.
```

### dispatch config

```yaml
dispatch:
  max_parallel: 10   # max concurrent tasks
  max_depth: 5       # max dispatch-within-dispatch nesting
  timeout_s: 300     # tasks that run over this get cancelled and return an error
```

---

## Pattern 5 — Sub-steps

Steps can contain sub-step folders with their own SKILL.md and tools.

```
step-02-process/
├── SKILL.md
├── tools/
├── sub-01-chunk/
│   └── SKILL.md
├── sub-02-embed/
│   └── SKILL.md
└── sub-03-index/
    └── SKILL.md
```

The parent step orchestrates by dispatching to sub-steps:

```markdown
## Task

For each document, run the three sub-steps in sequence:

1. dispatch_task with substep "sub-01-chunk" — splits into chunks
2. dispatch_task with substep "sub-02-embed" — embeds the chunks
3. dispatch_task with substep "sub-03-index" — adds to the index

You can parallelise the chunking across all documents at once.
```

SKILL.md stacks: the sub-step sees global SKILL.md + parent step SKILL.md + its own SKILL.md. The most specific wins on conflict.

Tool resolution: sub-step tools override step tools which override pipeline tools.

---

## Self-reflection

After a step completes, the runner can make one extra LLM call where the model reviews the full conversation and rewrites its own SKILL.md. The SKILL.md controls what the model looks for and what it writes — plain English.

Enable it in `pipeline.yaml`:

```yaml
self_reflection: true     # global opt-in (update mode)
self_reflection: report   # global opt-in (report mode — reads output only, SKILL.md unchanged)

steps:
  - id: step-01-ingest
    self_reflection: false   # step-level override
```

**Modes:**

| Mode | Behaviour |
|---|---|
| `true` / `update` | Model rewrites SKILL.md in place. Output also saved to `output/<step_id>/reflection.md`. |
| `report` | Model produces the proposed new SKILL.md but doesn't overwrite the original. Saved to `output/<step_id>/reflection.md` only. |

Write the reflection behaviour in the step's SKILL.md:

```markdown
## Self-Reflection

If any tool errors occurred, add a "## Lessons Learned" section
describing what failed and what path or approach to try instead.
One bullet per distinct failure. Skip if there were no errors.
```

After the step finishes, the runner sends the full conversation history back to the model. The model reads its SKILL.md `## Self-Reflection` section, follows those instructions, and outputs the complete new SKILL.md content — or `NO_CHANGES` if nothing is needed. If it outputs content, the runner writes it to `output/<step_id>/reflection.md` and (in `update` mode) replaces the live SKILL.md so the next run picks it up.

During reflection the model also has access to `get_run_usage` (token/cost totals) and `self_knowledge` (framework docs) if its instructions call for them.

The step decides what to learn, when to learn it, and how to write it. All in English.

---

## Human-in-the-loop

Steps can pause for human input. See [Human Input](human-input.md).

```yaml
- id: step-03-human-review
  human_input:
    mode: console
    prompt: "Review output/step-02/report.md and approve (yes/no):"
  can_goto:
    - step-04-output
    - step-02-process
```
