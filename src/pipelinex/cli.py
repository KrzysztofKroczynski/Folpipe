import os
import sys
from pathlib import Path

import click

# Force UTF-8 stdout/stderr on Windows (avoids charmap errors with model output)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@click.group()
def main():
    """folpipe — folder-based agentic AI pipeline framework

    Docs: https://github.com/kroczynskikrzysztof/pipelinex/tree/main/docs
    """


@main.command()
@click.argument("pipeline_path", type=click.Path(exists=True))
@click.option("--input", "input_data", default=None, help="Input text or path to input file")
@click.option("--from", "from_step", default=None, metavar="STEP_ID", help="Resume from this step")
@click.option("--dry-run", is_flag=True, help="Validate config and env, don't execute")
@click.option("--watch", is_flag=True, help="Show live step/tool progress")
@click.option("--model", "model_override", default=None, metavar="PROVIDER/NAME", help="Override model")
def run(pipeline_path, input_data, from_step, dry_run, watch, model_override):
    """Run a pipeline."""
    import logging
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    logging.getLogger("LiteLLM").propagate = False

    from .loader import load_pipeline, validate_pipeline
    from .runner import PipelineRunner

    path = Path(pipeline_path)

    try:
        config = load_pipeline(path)
    except (FileNotFoundError, SystemExit) as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    errors = validate_pipeline(config)
    if errors:
        click.echo("Validation errors:", err=True)
        for e in errors:
            click.echo(f"  - {e}", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("Pipeline config valid.")
        click.echo(f"  Name:    {config.get('name')}")
        click.echo(f"  Version: {config.get('version')}")
        click.echo(f"  Model:   {config['model']['provider']}/{config['model']['name']}")
        click.echo(f"  Steps:   {[s['id'] for s in config.get('steps', [])]}")
        return

    if input_data:
        p = Path(input_data)
        if p.exists():
            input_data = p.read_text(encoding="utf-8")

    runner = PipelineRunner(
        pipeline_path=path,
        watch=watch,
        from_step=from_step,
        model_override=model_override,
        input_data=input_data,
    )

    try:
        runner.run()
    except SystemExit as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)


def _find_pipeline_dir(start: Path = None) -> Path | None:
    d = (start or Path.cwd()).resolve()
    for candidate in [d, *d.parents]:
        if (candidate / "pipeline.yaml").exists():
            return candidate
    return None


def _resolve_pipeline_dir(in_dir: str | None) -> Path:
    if in_dir:
        return Path(in_dir)
    found = _find_pipeline_dir()
    if found:
        click.echo(f"Using pipeline: {found.name}")
        return found
    click.echo("ERROR: No pipeline.yaml found. Use --in to specify the pipeline directory.", err=True)
    sys.exit(1)


def _resolve_tools_dir(in_dir: str | None) -> Path:
    if in_dir:
        p = Path(in_dir)
        return p if p.name == "tools" else p / "tools"
    pipeline_dir = _resolve_pipeline_dir(None)
    return pipeline_dir / "tools"


@main.command()
@click.argument("args", nargs=-1)
@click.option("--in", "in_dir", default=None, help="Target directory")
def new(args, in_dir):
    """Scaffold a pipeline, step, or tool. Run with no args for interactive mode.

    \b
    folpipe new my-pipeline
    folpipe new step step-05-review
    folpipe new tool send_email
    """
    from .scaffold import scaffold_pipeline, scaffold_step, scaffold_tool

    if not args:
        kind = click.prompt("What to create", type=click.Choice(["pipeline", "step", "tool"]))
        name = click.prompt("Name")
        if kind == "pipeline":
            scaffold_pipeline(name, Path(in_dir or "."))
        elif kind == "step":
            scaffold_step(name, _resolve_pipeline_dir(in_dir))
        else:
            scaffold_tool(name, _resolve_tools_dir(in_dir))
        return

    if args[0] == "step":
        if len(args) < 2:
            click.echo("ERROR: provide a step name. Example: folpipe new step step-05-review", err=True)
            sys.exit(1)
        scaffold_step(args[1], _resolve_pipeline_dir(in_dir))

    elif args[0] == "tool":
        if len(args) < 2:
            click.echo("ERROR: provide a tool name. Example: folpipe new tool send_email", err=True)
            sys.exit(1)
        scaffold_tool(args[1], _resolve_tools_dir(in_dir))

    else:
        scaffold_pipeline(args[0], Path(in_dir or "."))


@main.group()
def add():
    """Add a step or tool to the current pipeline (auto-detects pipeline from cwd)."""


@add.command("step")
@click.argument("step_id")
@click.option("--in", "in_dir", default=None, help="Pipeline directory (default: auto-detect)")
def add_step(step_id, in_dir):
    """Add a step to a pipeline."""
    from .scaffold import scaffold_step
    scaffold_step(step_id, _resolve_pipeline_dir(in_dir))


@add.command("tool")
@click.argument("name")
@click.option("--in", "in_dir", default=None, help="Pipeline or tools directory (default: auto-detect)")
def add_tool(name, in_dir):
    """Add a tool to a pipeline."""
    from .scaffold import scaffold_tool
    scaffold_tool(name, _resolve_tools_dir(in_dir))


@main.command()
@click.argument("pipeline_path", type=click.Path(exists=True))
def validate(pipeline_path):
    """Validate pipeline config without running."""
    from .loader import load_pipeline, validate_pipeline

    path = Path(pipeline_path)
    try:
        config = load_pipeline(path)
    except (FileNotFoundError, SystemExit) as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    errors = validate_pipeline(config)
    if errors:
        click.echo("Validation failed:")
        for e in errors:
            click.echo(f"  x {e}")
        sys.exit(1)

    click.echo("OK Pipeline is valid")
    click.echo(f"  Steps: {[s['id'] for s in config.get('steps', [])]}")
    click.echo(f"  Model: {config['model']['provider']}/{config['model']['name']}")


@main.group()
def tools():
    """Manage tools."""


@tools.command("list")
@click.option("--pipeline", "pipeline_path", default=None, help="Include pipeline-level tools")
def tools_list(pipeline_path):
    """List available tools."""
    from .tools.builtin import BUILTIN_SCHEMAS
    from .tools.resolver import GLOBAL_TOOLS_PATH, resolve_tools

    click.echo("Built-in tools:")
    for t in BUILTIN_SCHEMAS:
        desc = t["description"].split(".")[0]
        click.echo(f"  {t['name']:<22} {desc}")

    if pipeline_path:
        path = Path(pipeline_path)
        custom = [t for t in resolve_tools(path) if t["name"] not in {s["name"] for s in BUILTIN_SCHEMAS}]
        if custom:
            click.echo(f"\nPipeline tools ({path.name}):")
            for t in custom:
                click.echo(f"  {t['name']}")

    if GLOBAL_TOOLS_PATH.exists():
        global_tools = list(GLOBAL_TOOLS_PATH.iterdir())
        if global_tools:
            click.echo(f"\nGlobal tools (~/.pipelinex/tools/):")
            for d in global_tools:
                if d.is_dir():
                    click.echo(f"  {d.name}")


@tools.command("install")
@click.argument("pipeline_path", type=click.Path(exists=True))
def tools_install(pipeline_path):
    """Install tool deps for a pipeline without running."""
    from .tools.resolver import install_tool_deps

    path = Path(pipeline_path)
    cache = Path.home() / ".pipelinex"
    count = 0

    for tools_dir in _all_tool_dirs(path):
        if not tools_dir.exists():
            continue
        for tool_dir in tools_dir.iterdir():
            if tool_dir.is_dir() and (tool_dir / "tool.json").exists():
                try:
                    install_tool_deps(tool_dir, cache)
                    count += 1
                except Exception as e:
                    click.echo(f"  Failed {tool_dir.name}: {e}", err=True)

    click.echo(f"Installed deps for {count} tool(s).")


def _all_tool_dirs(pipeline_path: Path):
    from .loader import load_pipeline

    yield pipeline_path / "tools"
    try:
        config = load_pipeline(pipeline_path)
        for step in config.get("steps", []):
            yield pipeline_path / step["id"] / "tools"
    except Exception:
        pass


_DOCS_DIR = Path(__file__).parent.parent.parent / "docs"


def _get_topics() -> dict[str, Path]:
    if not _DOCS_DIR.exists():
        return {}
    return {p.stem: p for p in sorted(_DOCS_DIR.glob("*.md"))}


@main.command()
@click.argument("topic", required=False, default=None)
def docs(topic):
    """Show documentation. Run without args to list topics.

    \b
    folpipe docs
    folpipe docs getting-started
    folpipe docs tools
    folpipe docs pipeline-structure
    """
    topics = _get_topics()

    if topic is None:
        if not topics:
            click.echo("No docs found.")
            return
        lines = ["Available topics:\n"]
        for name in topics:
            lines.append(f"  folpipe docs {name}")
        click.echo("\n".join(lines))
        return

    if topic not in topics:
        close = [t for t in topics if topic in t or t in topic]
        msg = f"Unknown topic: {topic!r}."
        if close:
            msg += f" Did you mean: {', '.join(close)}?"
        else:
            msg += f" Run 'folpipe docs' for the list."
        click.echo(msg, err=True)
        sys.exit(1)

    click.echo_via_pager(topics[topic].read_text(encoding="utf-8"))


@main.command()
@click.argument("pipeline_path", type=click.Path(exists=True))
@click.option("--errors", is_flag=True, help="Show error report from last failed run")
@click.option("--cost", is_flag=True, help="Show cost summary from last run")
def log(pipeline_path, errors, cost):
    """Show run log or error report."""
    import json as _json

    path = Path(pipeline_path)

    if cost:
        summary = path / "output" / "cost_summary.json"
        if summary.exists():
            data = _json.loads(summary.read_text(encoding="utf-8"))
            click.echo(
                f"Tokens: {data['total_tokens']:,} "
                f"({data['prompt_tokens']:,} in / {data['completion_tokens']:,} out)  "
                f"Cost: {data['cost']:.6f} {data['currency']}"
            )
        else:
            click.echo("No cost summary found. Run the pipeline first.")
    elif errors:
        report = path / "output" / "errors" / "report.md"
        if report.exists():
            click.echo(report.read_text(encoding="utf-8"))
        else:
            click.echo("No error report found.")
    else:
        log_file = path / "output" / "run.log"
        if log_file.exists():
            click.echo(log_file.read_text(encoding="utf-8"))
        else:
            click.echo("No run log found.")
