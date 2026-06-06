import json
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from functools import cached_property
from pathlib import Path

from .context_mgr import ContextBudgetExceeded, build_context_prompt
from .loader import load_pipeline, load_skill_md
from .logger import PipelineLogger
from .model import GET_RUN_USAGE_SCHEMA, SELF_KNOWLEDGE_SCHEMA, call_llm, check_tool_support, extract_text, extract_tool_calls, get_usage, reset_usage
from .state import State
from .tools.builtin import BUILTIN_NAMES, BUILTIN_SCHEMAS, BuiltinExecutor, PipelineCancelledError, Sandbox, self_knowledge
from .tools.executor import execute_custom_tool
from .tools.resolver import install_tool_deps, resolve_tools


def _build_diagnostics(llm_calls: int, tool_counts: dict[str, int], tool_errors: list[dict]) -> str:
    lines = ["## Step Diagnostics", "", f"- LLM calls: {llm_calls}"]
    if tool_counts:
        usage = ", ".join(f"{n} ×{c}" for n, c in sorted(tool_counts.items()))
        lines.append(f"- Tools used: {usage}")
    if tool_errors:
        lines.append(f"- Tool errors ({len(tool_errors)}):")
        for e in tool_errors:
            lines.append(f'  - {e["tool"]}: "{e["error"]}"')
    else:
        lines.append("- Tool errors: none")
    lines += [
        "",
        "Pay attention to these observations when deciding whether to update the SKILL.md.",
        "If the model used wrong tools, guessed paths, or looped unnecessarily, fix the instructions.",
    ]
    return "\n".join(lines)


def _strip_reflection_section(text: str) -> str:
    """Remove ## Self-Reflection section from SKILL.md before using it as the main step prompt."""
    m = re.search(r'\n*^## Self-Reflection\b', text, re.MULTILINE | re.IGNORECASE)
    if m:
        return text[:m.start()].rstrip()
    return text



class PipelineRunner:
    def __init__(
        self,
        pipeline_path: Path,
        watch: bool = False,
        from_step: str | None = None,
        model_override: str | None = None,
        input_data: str | None = None,
    ):
        self.pipeline_path = Path(pipeline_path)
        self.watch = watch
        self.from_step = from_step
        self.model_override = model_override
        self.input_data = input_data

        self.config = load_pipeline(pipeline_path)
        self.state = State(
            pipeline_path,
            resume=(from_step is not None),
            pipeline_version=self.config.get("version"),
        )

        output_path = self.pipeline_path / "output"
        self.logger = PipelineLogger(output_path, watch=watch)

        self.global_model = self.config["model"]

        dispatch_cfg = self.config.get("dispatch", {})
        self.max_parallel = dispatch_cfg.get("max_parallel", 10)
        self.max_depth = dispatch_cfg.get("max_depth", 5)
        self.dispatch_timeout = dispatch_cfg.get("timeout_s", 300)

        self._adhoc_names: dict[str, int] = {}
        self._adhoc_lock = threading.Lock()

    @cached_property
    def _sandbox(self) -> Sandbox:
        return Sandbox(self.pipeline_path)

    def _write_cancellation(self, err: PipelineCancelledError) -> None:
        out = self.pipeline_path / "output"
        out.mkdir(parents=True, exist_ok=True)
        state_snapshot = self.state.snapshot()
        lines = [
            "# Pipeline cancelled\n",
            f"**Step**: {err.step_id}",
            f"**Reason**: {err.reason}",
        ]
        if state_snapshot:
            lines += ["", "## State at cancellation", "```json", json.dumps(state_snapshot, indent=2, default=str), "```"]
        (out / "cancelled.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _install_deps(self):
        cache = Path.home() / ".pipelinex"
        tool_dirs: list[Path] = [self.pipeline_path / "tools"]
        for step in self.config.get("steps", []):
            tool_dirs.append(self.pipeline_path / step["id"] / "tools")

        pending = []
        for td in tool_dirs:
            if not td.exists():
                continue
            for tool_dir in td.iterdir():
                if tool_dir.is_dir() and (tool_dir / "tool.json").exists():
                    schema = json.loads((tool_dir / "tool.json").read_text(encoding="utf-8"))
                    if schema.get("deps"):
                        pending.append((tool_dir, schema["deps"]))

        if pending:
            all_deps = sorted({d for _, ds in pending for d in ds})
            print(f"Installing tool deps: {', '.join(all_deps)} ...")
            for tool_dir, _ in pending:
                try:
                    install_tool_deps(tool_dir, cache)
                except Exception as e:
                    print(f"  WARNING: dep install failed for {tool_dir.name}: {e}")

    def run(self):
        steps = self.config.get("steps", [])
        if not steps:
            raise SystemExit("ERROR: No steps defined.")

        step_map = {s["id"]: s for s in steps}
        step_ids = [s["id"] for s in steps]

        reset_usage()
        self._install_deps()
        check_tool_support(self.global_model)

        current_id = self.from_step or step_ids[0]
        iteration_count: dict[str, int] = {}

        while current_id:
            step_cfg = step_map.get(current_id)
            if not step_cfg:
                raise SystemExit(f"ERROR: Step '{current_id}' not found.")

            count = iteration_count.get(current_id, 0) + 1
            max_iter = step_cfg.get("max_iterations", 200)
            if count > max_iter:
                raise SystemExit(
                    f"ERROR: Step '{current_id}' exceeded max_iterations ({max_iter})."
                )
            iteration_count[current_id] = count

            if "human_input" in step_cfg:
                self._collect_human_input(step_cfg)

            try:
                next_id = self._run_step(step_cfg)
            except PipelineCancelledError as e:
                self._write_cancellation(e)
                usage = get_usage()
                self.logger.cost_summary(usage)
                print(
                    f"Pipeline cancelled in '{e.step_id}': {e.reason}\n"
                    f"Tokens: {usage['total_tokens']:,} "
                    f"({usage['prompt_tokens']:,} in / {usage['completion_tokens']:,} out)  "
                    f"Cost: {usage['cost']:.6f} {usage['currency']}"
                )
                return
            except ContextBudgetExceeded as e:
                raise SystemExit(f"ERROR: context budget exceeded in step '{current_id}': {e}")
            self.state.mark_step_complete(current_id)

            if step_cfg.get("terminal"):
                usage = get_usage()
                self.logger.cost_summary(usage)
                print(
                    f"Pipeline complete.  "
                    f"Tokens: {usage['total_tokens']:,} "
                    f"({usage['prompt_tokens']:,} in / {usage['completion_tokens']:,} out)  "
                    f"Cost: {usage['cost']:.6f} {usage['currency']}"
                )
                break

            if next_id:
                can_goto = step_cfg.get("can_goto", [])
                if can_goto and next_id not in can_goto:
                    raise SystemExit(
                        f"ERROR: Model routed to '{next_id}' from '{current_id}', "
                        f"not in can_goto: {can_goto}"
                    )
                current_id = next_id
            else:
                try:
                    idx = step_ids.index(current_id)
                    current_id = step_ids[idx + 1] if idx + 1 < len(step_ids) else None
                except (ValueError, IndexError):
                    current_id = None

    def _run_step(self, step_cfg: dict) -> str | None:
        step_id = step_cfg["id"]
        model_cfg = step_cfg.get("model", self.global_model)
        if self.model_override:
            model_cfg = self._apply_model_override(self.model_override, model_cfg)

        self.logger.step_start(step_id)
        self.state.set_current_step(step_id)

        skill_md = load_skill_md(self.pipeline_path, step_id)
        handoff = self.state.get_handoff()
        token_budget = step_cfg.get("context_budget_tokens", self.config.get("context_budget_tokens"))
        context = build_context_prompt(
            self.state.snapshot(), skill_md, handoff,
            model_cfg=model_cfg, token_budget=token_budget,
        )

        system = _strip_reflection_section(skill_md)

        env_block = (
            f"## Runtime Environment\n\n"
            f"- Pipeline root: `{self.pipeline_path}`\n"
            f"- Your output folder: `output/{step_id}/`\n"
            f"- Shared state: `output/state.json`\n"
            f"- Input folder: `input/`\n"
        )
        system += "\n\n---\n\n" + env_block

        if context:
            system += "\n\n---\n\n## Current State\n\n" + context

        can_goto = step_cfg.get("can_goto", [])
        if can_goto:
            system += (
                f"\n\n---\n\nWhen you finish this step, output a JSON block with the next step:\n"
                f"```json\n{{\"next\": \"<step-id>\", \"reason\": \"<why>\"}}\n```\n"
                f"Valid next steps: {can_goto}"
            )

        user_content = "Begin this step."
        if self.input_data and not self.state.get("_input_consumed"):
            user_content += f"\n\nInput:\n{self.input_data}"
            self.state.set("_input_consumed", True)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        self.logger.context_snapshot(step_id, context)

        # Resolve tools for this step
        all_tools = resolve_tools(
            self.pipeline_path,
            step_id=step_id,
            builtin_tools=list(BUILTIN_SCHEMAS),
        )
        llm_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in all_tools
        ]
        custom_by_name = {
            t["name"]: t for t in all_tools if t["name"] not in BUILTIN_NAMES and "_path" in t
        }

        builtin_exec = BuiltinExecutor(
            state=self.state,
            pipeline_path=self.pipeline_path,
            step_id=step_id,
            model_config=model_cfg,
            logger=self.logger,
            sandbox=self._sandbox,
        )

        step_output = self.pipeline_path / "output" / step_id
        step_output.mkdir(parents=True, exist_ok=True)

        last_text = ""
        retries_for_routing = 0
        llm_call_count = 0
        tool_counts: dict[str, int] = {}
        tool_errors: list[dict] = []

        try:
            while True:
                response = call_llm(model_cfg, messages, tools=llm_tools)
                llm_call_count += 1

                text = extract_text(response)
                tool_calls = extract_tool_calls(response)

                if text:
                    last_text = text
                    self.logger.model_response(step_id, text)

                if not tool_calls:
                    # Step complete
                    next_step = None
                    if can_goto:
                        next_step = self._extract_next(text)
                        if next_step is None:
                            # Retry once per spec
                            if retries_for_routing < 1:
                                retries_for_routing += 1
                                messages.append({"role": "assistant", "content": text})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "Please output the routing JSON block to indicate "
                                        f"which step to go to next. Valid: {can_goto}"
                                    ),
                                })
                                continue
                            else:
                                raise RuntimeError(
                                    f"Step '{step_id}' did not produce a valid routing decision "
                                    f"after retry. Expected JSON with 'next' from {can_goto}."
                                )
                    mode = self._get_reflection_mode(step_cfg)
                    if mode:
                        diagnostics = _build_diagnostics(llm_call_count, tool_counts, tool_errors)
                        self._self_reflect(step_id, messages, model_cfg, mode, diagnostics=diagnostics)
                    self.logger.step_end(step_id, next_step)
                    return next_step

                # Add assistant message with tool calls
                messages.append(self._build_assistant_msg(text, tool_calls))

                # Separate dispatch calls from others
                dispatch_calls = [tc for tc in tool_calls if tc["name"] == "dispatch_task"]
                other_calls = [tc for tc in tool_calls if tc["name"] != "dispatch_task"]

                # Execute non-dispatch tools sequentially
                for tc in other_calls:
                    self.logger.tool_call(step_id, tc["name"], tc["args"])
                    if tc["name"] in BUILTIN_NAMES:
                        result = builtin_exec.execute(tc["name"], tc["args"])
                    elif tc["name"] in custom_by_name:
                        tool_dir = Path(custom_by_name[tc["name"]]["_path"])
                        result = execute_custom_tool(tool_dir, tc["args"], env=self.config.get("_env"))
                    else:
                        result = {"error": f"Unknown tool: {tc['name']}"}
                    tool_counts[tc["name"]] = tool_counts.get(tc["name"], 0) + 1
                    if "error" in result:
                        tool_errors.append({"tool": tc["name"], "error": result["error"]})
                    self.logger.tool_result(step_id, tc["name"], result)
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result, default=str),
                        "tool_call_id": tc["id"],
                    })

                # Execute dispatch calls (parallel if multiple)
                if dispatch_calls:
                    tool_counts["dispatch_task"] = tool_counts.get("dispatch_task", 0) + len(dispatch_calls)
                    if len(dispatch_calls) == 1:
                        result = self._dispatch_one(dispatch_calls[0]["args"], model_cfg, parent_step_id=step_id)
                        self.logger.tool_result(step_id, "dispatch_task", result)
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(result, default=str),
                            "tool_call_id": dispatch_calls[0]["id"],
                        })
                    else:
                        results = self._dispatch_parallel(dispatch_calls, model_cfg, parent_step_id=step_id)
                        for tc, result in zip(dispatch_calls, results):
                            self.logger.tool_result(step_id, "dispatch_task", result)
                            messages.append({
                                "role": "tool",
                                "content": json.dumps(result, default=str),
                                "tool_call_id": tc["id"],
                            })

        except PipelineCancelledError:
            raise
        except Exception as e:
            mode = self._get_reflection_mode(step_cfg)
            if mode:
                try:
                    diagnostics = _build_diagnostics(llm_call_count, tool_counts, tool_errors)
                    self._self_reflect(step_id, messages, model_cfg, mode, diagnostics=diagnostics)
                except Exception:
                    pass
            self.logger.error(
                step_id,
                str(e),
                state=self.state.snapshot(),
                last_response=last_text,
            )
            raise

    def _get_reflection_mode(self, step_cfg: dict) -> str | None:
        global_default = self.config.get("self_reflection", False)
        val = step_cfg.get("self_reflection", global_default)
        if not val:
            return None
        if val == "report":
            return "report"
        return "update"

    def _self_reflect(self, step_id: str, messages: list[dict], model_cfg: dict, mode: str = "update", diagnostics: str = "") -> None:
        skill_path = self.pipeline_path / step_id / "SKILL.md"
        if not skill_path.exists():
            return

        skill_content = skill_path.read_text(encoding="utf-8")

        if mode == "report":
            action_instruction = (
                "Output the complete proposed new SKILL.md text — the full content as it should read after your improvements. "
                "This will be saved as a report; the original SKILL.md will not be changed."
            )
        else:
            action_instruction = (
                "Output the complete improved SKILL.md text — the full content as it should read. "
                "This will replace your current SKILL.md."
            )

        diag_section = f"\n\n{diagnostics}" if diagnostics else ""

        reflection_messages = (
            [{"role": "system", "content": skill_content}]
            + messages[1:]
            + [{
                "role": "user",
                "content": (
                    f"This step has now ended. Review the conversation above against your SKILL.md.{diag_section}\n\n"
                    "Follow any self-reflection instructions in your SKILL.md. "
                    "Call any tools you need first (e.g. get_run_usage to check token and cost totals).\n\n"
                    f"{action_instruction}\n\n"
                    "If there are NO improvements to make, respond with exactly: NO_CHANGES\n"
                    "Otherwise output only the SKILL.md text — no preamble, no explanation."
                ),
            }]
        )

        final_text = ""
        while True:
            response = call_llm(model_cfg, reflection_messages, tools=[GET_RUN_USAGE_SCHEMA, SELF_KNOWLEDGE_SCHEMA])
            text = extract_text(response).strip()
            tool_calls = extract_tool_calls(response)

            if not tool_calls:
                final_text = text
                break

            reflection_messages.append(self._build_assistant_msg(text, tool_calls))
            for tc in tool_calls:
                if tc["name"] == "get_run_usage":
                    result = get_usage()
                elif tc["name"] == "self_knowledge":
                    result = self_knowledge(tc["args"].get("topic", ""))
                else:
                    result = {"error": f"Tool '{tc['name']}' not available during self-reflection"}
                reflection_messages.append({
                    "role": "tool",
                    "content": json.dumps(result, default=str),
                    "tool_call_id": tc["id"],
                })

        if not final_text or "NO_CHANGES" in final_text:
            return

        # Strip markdown code fences if model wrapped the output
        fenced = re.match(r'^```(?:markdown)?\n([\s\S]*?)```\s*$', final_text)
        if fenced:
            final_text = fenced.group(1)

        # Must look like a SKILL.md (starts with a markdown heading); otherwise the model
        # output prose instead of the improved file content — treat as no changes
        if not re.match(r'^#', final_text.strip()):
            return

        final_text = final_text.rstrip() + "\n"
        out = self.pipeline_path / "output" / step_id
        out.mkdir(parents=True, exist_ok=True)

        if mode == "update":
            skill_path.write_text(final_text, encoding="utf-8")

        (out / "reflection.md").write_text(final_text, encoding="utf-8")

    def _build_assistant_msg(self, text: str, tool_calls: list[dict]) -> dict:
        msg: dict = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls
            ]
        return msg

    def _extract_next(self, text: str) -> str | None:
        if not text:
            return None
        # Try fenced JSON block first
        m = re.search(r'```(?:json)?\s*(\{[^`]+\})\s*```', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if "next" in data:
                    return data["next"]
            except json.JSONDecodeError:
                pass
        # Inline JSON object
        for m in re.finditer(r'\{[^{}]*"next"\s*:\s*"([^"]+)"[^{}]*\}', text):
            return m.group(1)
        return None

    def _dispatch_one(self, args: dict, model_cfg: dict, depth: int = 0, parent_step_id: str | None = None) -> dict:
        if depth >= self.max_depth:
            return {"error": f"Max dispatch depth ({self.max_depth}) exceeded"}

        task = args.get("task", "")
        substep = args.get("substep", "")
        skill = args.get("skill", "")
        context = args.get("context", {})

        if substep and parent_step_id:
            substep_dir = self.pipeline_path / parent_step_id / substep
            if (substep_dir / "SKILL.md").exists():
                skill_md = load_skill_md(self.pipeline_path, parent_step_id, substep_id=substep)
                all_tools = resolve_tools(
                    self.pipeline_path,
                    step_id=parent_step_id,
                    substep_id=substep,
                    builtin_tools=list(BUILTIN_SCHEMAS),
                )
                return self._run_substep(task, skill_md, context, all_tools, model_cfg, depth, step_id=parent_step_id)
            return {"error": f"Sub-step '{substep}' not found under '{parent_step_id}'"}

        name = args.get("name", "") or task[:40]
        adhoc_id = self._resolve_adhoc_name(name, parent_step_id)
        output_step_id = f"{parent_step_id}/{adhoc_id}" if parent_step_id else adhoc_id
        all_tools = resolve_tools(
            self.pipeline_path,
            step_id=parent_step_id,
            builtin_tools=list(BUILTIN_SCHEMAS),
        )
        skill_md = skill or "Complete the given task concisely and accurately."
        return self._run_substep(task, skill_md, context, all_tools, model_cfg, depth, step_id=output_step_id)

    def _resolve_adhoc_name(self, name: str, parent_step_id: str | None) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")[:40] or "adhoc"
        scope = parent_step_id or ""
        with self._adhoc_lock:
            key = f"{scope}/{slug}"
            count = self._adhoc_names.get(key, 0)
            self._adhoc_names[key] = count + 1
        return slug if count == 0 else f"{slug}-{count}"

    def _run_substep(self, task: str, skill_md: str, context: dict, all_tools: list[dict], model_cfg: dict, depth: int, step_id: str = "") -> dict:
        system = skill_md
        if context:
            system += f"\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

        llm_tools = [
            {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {"type": "object", "properties": {}})}
            for t in all_tools
        ]
        custom_by_name = {t["name"]: t for t in all_tools if t["name"] not in BUILTIN_NAMES and "_path" in t}
        builtin_exec = BuiltinExecutor(
            state=self.state,
            pipeline_path=self.pipeline_path,
            step_id=step_id,
            model_config=model_cfg,
            logger=self.logger,
            sandbox=self._sandbox,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]
        try:
            while True:
                response = call_llm(model_cfg, messages, tools=llm_tools)
                text = extract_text(response)
                tool_calls = extract_tool_calls(response)

                if not tool_calls:
                    return {"result": text, "ok": True}

                messages.append(self._build_assistant_msg(text, tool_calls))

                dispatch_calls = [tc for tc in tool_calls if tc["name"] == "dispatch_task"]
                other_calls = [tc for tc in tool_calls if tc["name"] != "dispatch_task"]

                for tc in other_calls:
                    if tc["name"] in BUILTIN_NAMES:
                        result = builtin_exec.execute(tc["name"], tc["args"])
                    elif tc["name"] in custom_by_name:
                        result = execute_custom_tool(Path(custom_by_name[tc["name"]]["_path"]), tc["args"], env=self.config.get("_env"))
                    else:
                        result = {"error": f"Unknown tool: {tc['name']}"}
                    messages.append({"role": "tool", "content": json.dumps(result, default=str), "tool_call_id": tc["id"]})

                if dispatch_calls:
                    if len(dispatch_calls) == 1:
                        result = self._dispatch_one(dispatch_calls[0]["args"], model_cfg, depth + 1)
                        messages.append({"role": "tool", "content": json.dumps(result, default=str), "tool_call_id": dispatch_calls[0]["id"]})
                    else:
                        results = self._dispatch_parallel(dispatch_calls, model_cfg, depth + 1)
                        for tc, result in zip(dispatch_calls, results):
                            messages.append({"role": "tool", "content": json.dumps(result, default=str), "tool_call_id": tc["id"]})
        except Exception as e:
            return {"error": str(e), "ok": False}

    def _dispatch_parallel(self, dispatch_calls: list[dict], model_cfg: dict, depth: int = 0, parent_step_id: str | None = None) -> list[dict]:
        workers = min(len(dispatch_calls), self.max_parallel)
        results: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_to_id: dict[Future, str] = {
                ex.submit(self._dispatch_one, tc["args"], model_cfg, depth, parent_step_id): tc["id"]
                for tc in dispatch_calls
            }
            try:
                for future in as_completed(future_to_id, timeout=self.dispatch_timeout):
                    call_id = future_to_id[future]
                    try:
                        results[call_id] = future.result()
                    except Exception as e:
                        results[call_id] = {"error": str(e), "ok": False}
            except FuturesTimeoutError:
                for future, call_id in future_to_id.items():
                    if call_id not in results:
                        future.cancel()
                        results[call_id] = {
                            "error": f"Timed out after {self.dispatch_timeout}s",
                            "ok": False,
                        }

        return [results[tc["id"]] for tc in dispatch_calls]

    def _collect_human_input(self, step_cfg: dict):
        cfg = step_cfg.get("human_input", {})
        mode = cfg.get("mode", "console")
        prompt = cfg.get("prompt", "")
        step_id = step_cfg["id"]

        if mode == "console":
            print(f"\n{'=' * 60}\nSTEP: {step_id}\n{'=' * 60}")
            print(prompt)
            print("-" * 60)
            response = input("Your response: ").strip()
            self.state.set("human_input", response)

        elif mode == "file":
            step_out = self.pipeline_path / "output" / step_id
            step_out.mkdir(parents=True, exist_ok=True)
            waiting = step_out / "waiting.md"
            waiting.write_text(f"# Waiting for human input\n\n{prompt}", encoding="utf-8")
            print(f"\nEdit {waiting} then press Enter...")
            input()
            decision = step_out / "decision.md"
            if decision.exists():
                self.state.set("human_input", decision.read_text(encoding="utf-8"))

        elif mode == "tool":
            tool_name = cfg.get("tool")
            if not tool_name:
                raise SystemExit(
                    f"ERROR: human_input mode=tool in step '{step_id}' has no 'tool' specified."
                )
            all_tools = resolve_tools(self.pipeline_path, step_id=step_id)
            tool = next((t for t in all_tools if t["name"] == tool_name and "_path" in t), None)
            if tool is None:
                raise SystemExit(
                    f"ERROR: human_input tool '{tool_name}' not found for step '{step_id}'."
                )
            result = execute_custom_tool(
                Path(tool["_path"]), {"prompt": prompt}, env=self.config.get("_env")
            )
            if "error" in result:
                raise SystemExit(
                    f"ERROR: human_input tool '{tool_name}' failed: {result['error']}"
                )
            response = result.get("response") or result.get("result") or json.dumps(result)
            self.state.set("human_input", response)

        else:
            raise SystemExit(
                f"ERROR: Unknown human_input mode '{mode}' in step '{step_id}'. "
                "Valid modes: console, file, tool."
            )

    def _apply_model_override(self, override: str, base: dict) -> dict:
        cfg = dict(base)
        if "/" in override:
            provider, name = override.split("/", 1)
            cfg["provider"] = provider
            cfg["name"] = name
        else:
            cfg["name"] = override
        return cfg
