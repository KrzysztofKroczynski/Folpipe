import os
import re
from pathlib import Path

import yaml
from dotenv import dotenv_values


def load_env(pipeline_path: Path) -> dict:
    env = dict(os.environ)
    env_file = pipeline_path / ".env"
    if env_file.exists():
        env.update(dotenv_values(env_file))
    return env


def _substitute(obj, env: dict):
    if isinstance(obj, str):
        def replace(m):
            var = m.group(1)
            if var not in env:
                raise EnvironmentError(
                    f"Missing environment variable: {var}\n"
                    f"       Add it to .env or export it in your shell."
                )
            return env[var]
        return re.sub(r'\$\{([^}]+)\}', replace, obj)
    elif isinstance(obj, dict):
        return {k: _substitute(v, env) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute(i, env) for i in obj]
    return obj


def load_pipeline(pipeline_path: Path) -> dict:
    pipeline_path = Path(pipeline_path)
    yaml_file = pipeline_path / "pipeline.yaml"
    if not yaml_file.exists():
        raise FileNotFoundError(f"pipeline.yaml not found in {pipeline_path}")

    env = load_env(pipeline_path)

    with open(yaml_file) as f:
        raw = yaml.safe_load(f)

    try:
        config = _substitute(raw, env)
    except EnvironmentError as e:
        raise SystemExit(f"ERROR: {e}")

    config["_path"] = pipeline_path
    config["_env"] = env
    return config


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    # Find closing marker: must be \n---\n or \n--- at end of file
    m = re.search(r'\n---(\n|$)', text[3:])
    if m:
        return text[3 + m.end():].lstrip("\n")
    return text


def load_skill_md(pipeline_path: Path, step_id: str | None = None, substep_id: str | None = None) -> str:
    parts = []

    global_skill = pipeline_path / "SKILL.md"
    if global_skill.exists():
        parts.append(_strip_frontmatter(global_skill.read_text(encoding="utf-8")))

    if step_id:
        step_skill = pipeline_path / step_id / "SKILL.md"
        if step_skill.exists():
            parts.append(_strip_frontmatter(step_skill.read_text(encoding="utf-8")))

        if substep_id:
            substep_skill = pipeline_path / step_id / substep_id / "SKILL.md"
            if substep_skill.exists():
                parts.append(_strip_frontmatter(substep_skill.read_text(encoding="utf-8")))

    return "\n\n---\n\n".join(parts)


def validate_pipeline(config: dict) -> list[str]:
    errors = []

    if "model" not in config:
        errors.append("Missing 'model' section")
    else:
        if "provider" not in config["model"]:
            errors.append("model.provider is required")
        if "name" not in config["model"]:
            errors.append("model.name is required")

    if not config.get("steps"):
        errors.append("No steps defined")
    else:
        step_ids = {s["id"] for s in config["steps"] if "id" in s}
        for step in config["steps"]:
            if "id" not in step:
                errors.append(f"Step missing 'id': {step}")
                continue
            for target in step.get("can_goto", []):
                if target not in step_ids:
                    errors.append(
                        f"Step '{step['id']}' can_goto '{target}' which doesn't exist"
                    )

    return errors
