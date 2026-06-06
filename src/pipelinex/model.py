import json
import logging
import os
import threading

os.environ.setdefault("LITELLM_LOG", "ERROR")

# Block LiteLLM startup warnings (botocore/sagemaker) before import fires them
_litellm_logger = logging.getLogger("LiteLLM")
_litellm_logger.setLevel(logging.ERROR)
_litellm_logger.propagate = False

import litellm

litellm.drop_params = True


class _UsageAccumulator:
    def __init__(self):
        self._lock = threading.Lock()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.currency = "USD"

    def add(self, prompt: int, completion: int, cost: float, currency: str = "USD"):
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.cost += cost
            self.currency = currency

    def reset(self):
        with self._lock:
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.cost = 0.0
            self.currency = "USD"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
                "cost": round(self.cost, 6),
                "currency": self.currency,
            }


_usage = _UsageAccumulator()


def get_usage() -> dict:
    return _usage.snapshot()


def reset_usage():
    _usage.reset()


GET_RUN_USAGE_SCHEMA = {
    "name": "get_run_usage",
    "description": (
        "Return token and cost usage accumulated so far in this pipeline run. "
        "Only available during self-reflection. Use to check token or cost efficiency for this step."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SELF_KNOWLEDGE_SCHEMA = {
    "name": "self_knowledge",
    "description": (
        "Read folpipe framework documentation. Use it to look up available tools, "
        "pipeline configuration options, execution patterns, and best practices. "
        "Omit 'topic' to list all available topics."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": (
                    "Documentation topic to read (e.g. 'tools', 'pipeline-structure', "
                    "'context-management', 'execution-patterns', 'state', 'cli'). "
                    "Omit to list all available topics."
                ),
            }
        },
        "required": [],
    },
}


def _model_str(cfg: dict) -> str:
    provider = cfg["provider"]
    name = cfg["name"]
    if provider == "anthropic":
        return f"anthropic/{name}"
    if provider in ("ollama",):
        return f"ollama/{name}"
    if provider == "groq":
        return f"groq/{name}"
    if provider == "bedrock":
        return f"bedrock/{name}"
    if provider == "openai":
        return name
    return f"{provider}/{name}"


def _litellm_kwargs(cfg: dict) -> dict:
    kw = {"model": _model_str(cfg)}
    if "api_key" in cfg:
        kw["api_key"] = cfg["api_key"]
    if "base_url" in cfg:
        kw["base_url"] = cfg["base_url"]
    return kw


def check_tool_support(cfg: dict):
    model = _model_str(cfg)
    try:
        if not litellm.supports_function_calling(model=model):
            raise SystemExit(
                f'ERROR: model "{cfg.get("name", model)}" does not support tool calling.\n'
                f"       Tool calling is required. Use a model that supports it."
            )
    except SystemExit:
        raise
    except Exception:
        pass  # can't verify — let it fail at runtime


def call_llm(cfg: dict, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 4096):
    kw = _litellm_kwargs(cfg)
    kw["messages"] = messages
    kw["max_tokens"] = max_tokens

    if tools:
        kw["tools"] = [{"type": "function", "function": t} for t in tools]
        kw["tool_choice"] = "auto"

    fallback = cfg.get("fallback")
    active_cfg = cfg
    try:
        resp = litellm.completion(**kw)
    except Exception:
        if not fallback:
            raise
        fb_kw = _litellm_kwargs(fallback)
        fb_kw["messages"] = messages
        fb_kw["max_tokens"] = max_tokens
        if tools:
            fb_kw["tools"] = kw["tools"]
            fb_kw["tool_choice"] = "auto"
        resp = litellm.completion(**fb_kw)
        active_cfg = fallback

    try:
        u = resp.usage
        prompt = getattr(u, "prompt_tokens", 0) or 0
        completion = getattr(u, "completion_tokens", 0) or 0
        try:
            cost = litellm.completion_cost(completion_response=resp) or 0.0
        except Exception:
            cost = 0.0
        pricing = active_cfg.get("pricing", {})
        if cost == 0.0 and pricing:
            inp = pricing.get("input_per_million", 0.0)
            out = pricing.get("output_per_million", 0.0)
            cost = (prompt * inp + completion * out) / 1_000_000
            currency = pricing.get("currency", "USD")
        else:
            currency = "USD"
        _usage.add(prompt, completion, cost, currency)
    except Exception:
        pass

    return resp.choices[0].message


def extract_tool_calls(message) -> list[dict]:
    if not getattr(message, "tool_calls", None):
        return []
    calls = []
    for tc in message.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            args = {}
        calls.append({"id": tc.id, "name": tc.function.name, "args": args})
    return calls


def extract_text(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content or ""
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""
