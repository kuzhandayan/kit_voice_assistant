import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessage

from app.core.config import Settings
from app.services.resilience import Attempt, FallbackResult, with_fallback

logger = logging.getLogger(__name__)

PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}
# Gemini 3 rejects tool-call history it did not sign itself, so tool turns are sent to it as plain text.
FLATTEN_TOOL_HISTORY = {"gemini"}
DEFAULT_COOLDOWN_SECONDS = 20.0
MAX_OUTPUT_TOKENS = 300


@dataclass(frozen=True)
class ChainEntry:
    vendor: str
    model: str
    reasoning_effort: str | None = None


def parse_chain(chain: str, keys: dict[str, str]) -> list[ChainEntry]:
    """Format: vendor:model[@reasoning_effort], comma separated, in fallback order."""
    entries: list[ChainEntry] = []
    for item in (i.strip() for i in chain.split(",")):
        vendor, _, rest = item.partition(":")
        model, _, effort = rest.partition("@")
        if vendor in PROVIDER_URLS and model and keys.get(vendor):
            entries.append(ChainEntry(vendor, model, effort or None))
        elif item:
            logger.info("Skipping LLM '%s' (unknown vendor or missing key)", item)
    return entries


def flatten_tool_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrites assistant tool calls and tool results as plain text turns."""
    names: dict[str, str] = {}
    flat: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                names[call["id"]] = call["function"]["name"]
                calls.append(f"{call['function']['name']}({call['function']['arguments']})")
            flat.append({"role": "assistant", "content": f"(I called: {', '.join(calls)})"})
        elif message.get("role") == "tool":
            name = names.get(message.get("tool_call_id", ""), "tool")
            flat.append({"role": "user", "content": f"[Result of {name}]: {message['content']}"})
        else:
            flat.append(message)
    return flat


def _retry_after(exc: RateLimitError) -> float:
    try:
        return min(float(exc.response.headers.get("retry-after", DEFAULT_COOLDOWN_SECONDS)), 60.0)
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS


@dataclass
class LLMProvider:
    name: str
    vendor: str
    client: AsyncOpenAI
    model: str
    extra: dict[str, Any] = field(default_factory=dict)
    cooldown_until: float = 0.0

    @property
    def cooling_down(self) -> bool:
        return time.monotonic() < self.cooldown_until

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatCompletionMessage:
        if self.vendor in FLATTEN_TOOL_HISTORY:
            messages = flatten_tool_history(messages)
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                temperature=0.2,
                max_tokens=MAX_OUTPUT_TOKENS,
                **self.extra,
            )
        except RateLimitError as exc:
            self.cooldown_until = time.monotonic() + _retry_after(exc)
            raise
        return response.choices[0].message


class LLMRouter:
    """Tries each configured provider in order. Rate-limited providers are skipped until their cooldown ends."""

    def __init__(self, providers: list[LLMProvider], timeout: float):
        self._providers = providers
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMRouter":
        keys = {"groq": settings.groq_api_key, "gemini": settings.gemini_api_key}
        clients: dict[str, AsyncOpenAI] = {}
        providers = []
        for entry in parse_chain(settings.llm_chain, keys):
            client = clients.setdefault(
                entry.vendor,
                AsyncOpenAI(api_key=keys[entry.vendor], base_url=PROVIDER_URLS[entry.vendor], max_retries=0),
            )
            extra = {"reasoning_effort": entry.reasoning_effort} if entry.reasoning_effort else {}
            providers.append(LLMProvider(f"{entry.vendor}:{entry.model}", entry.vendor, client, entry.model, extra))
        return cls(providers, settings.llm_timeout_seconds)

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> FallbackResult[ChatCompletionMessage]:
        ready = [p for p in self._providers if not p.cooling_down] or self._providers
        attempts = [Attempt(p.name, lambda p=p: p.complete(messages, tools)) for p in ready]
        return await with_fallback(attempts, timeout=self._timeout, label="LLM")


def tool_result_json(output: dict[str, Any], limit: int) -> str:
    text = json.dumps(output, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 20] + '..."(truncated)"}'
