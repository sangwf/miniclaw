from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from llm import LLMClient, Usage
from session import SessionState
from tools import ToolRegistry


DEFAULT_SYSTEM_PROMPT = (
    "You are miniclaw, a concise and practical coding assistant operating inside one workspace. "
    "Use tools whenever repository inspection, file changes, or command execution are needed. "
    "When the user needs current or external information, use web_search and then web_fetch instead of guessing. "
    "For interactive or dynamic webpages, prefer browser_navigate, browser_snapshot, browser_act, and browser_extract instead of guessing or relying only on web_fetch. "
    "If the user explicitly asks for browser actions on a site or page, execute those browser steps in order instead of jumping directly to a guessed destination URL. "
    "When a relevant page is already open in the browser session, inspect it with browser_snapshot or browser_extract before falling back to generic web tools. "
    "For recent tweets or direct Twitter/X account lookups, prefer twitter_user_posts, twitter_tweet, and twitter_whoami over generic web tools. "
    "The workspace has a persistent Markdown memory at .miniclaw/memory.md. "
    "Use memory_read, memory_replace, and memory_forget for durable preferences, workspace rules, and stable facts. "
    "Do not save transient search results, command output, or task-local notes to memory. "
    "Do not guess file contents. Read before editing, then verify with commands when changes matter. "
    "If the user wants to work in another directory, call set_workspace. "
    "Prefer run_python for quick calculations or temporary validation logic. "
    "Prefer write_temp_file for scratch scripts; avoid leaving temporary files in the workspace root. "
    "Prefer apply_patch for editing existing files. "
    "Use write_file only for new files or intentional full rewrites. "
    "If a patch fails, re-read the file and try again with more precise context. "
    "Keep user-facing replies short and concrete."
)


@dataclass(frozen=True)
class ToolExecutionEvent:
    phase: str
    tool_name: str
    arguments: str
    result: str | None = None


ToolEventHandler = Callable[[ToolExecutionEvent], None]


@dataclass(frozen=True)
class LLMUsageEvent:
    usage: Usage
    stage: str
    tool_calls_requested: bool


LLMUsageHandler = Callable[[LLMUsageEvent], None]


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        session: SessionState,
        tools: ToolRegistry,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_tool_round_trips: int = 20,
        tool_event_handler: ToolEventHandler | None = None,
        llm_usage_handler: LLMUsageHandler | None = None,
    ) -> None:
        self.llm = llm
        self.session = session
        self.tools = tools
        self.max_tool_round_trips = max_tool_round_trips
        self.tool_event_handler = tool_event_handler
        self.llm_usage_handler = llm_usage_handler
        self.history: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    def run_turn(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        self.session.append_transcript("user", user_text)
        turn_notes = [
            "Use tools deliberately. If you already have enough evidence to answer, answer now."
        ]
        browser_sequence_note = self._browser_sequence_note(user_text)
        if browser_sequence_note:
            turn_notes.append(browser_sequence_note)

        for round_index in range(self.max_tool_round_trips):
            budget_remaining = self.max_tool_round_trips - round_index
            output = self.llm.generate(
                self._messages_with_runtime_state(
                    tool_budget_remaining=budget_remaining,
                    extra_notes=turn_notes,
                ),
                self.tools.openai_tools(),
            )
            self._emit_llm_usage(stage="loop", output=output)

            if not output.tool_calls:
                reply = self._clean_reply(output.text.strip()) or "(empty response)"
                self.history.append({"role": "assistant", "content": reply})
                self.session.append_transcript("assistant", reply)
                return reply

            self.history.append(
                {
                    "role": "assistant",
                    "content": output.text or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in output.tool_calls
                    ],
                }
            )

            for call in output.tool_calls:
                self._emit_tool_event(ToolExecutionEvent("start", call.name, call.arguments))
                result = self.tools.run(call.name, call.arguments)
                self._emit_tool_event(ToolExecutionEvent("finish", call.name, call.arguments, result))
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )

        # Give the model one last chance to synthesize an answer from the
        # accumulated tool results without requesting more tools.
        final_output = self.llm.generate(
            self._messages_with_runtime_state(
                tool_budget_remaining=0,
                extra_notes=[
                    "Tool budget for this turn is exhausted.",
                    "Do not emit tool calls, JSON tool stubs, or pseudo-tool plans.",
                    "Give the best final answer using only the evidence already gathered.",
                ],
            ),
            tools=None,
        )
        self._emit_llm_usage(stage="final", output=final_output)
        reply = self._clean_reply(final_output.text.strip()) or "Tool loop limit reached."
        self.history.append({"role": "assistant", "content": reply})
        self.session.append_transcript("assistant", reply)
        return reply

    def _messages_with_runtime_state(
        self,
        *,
        tool_budget_remaining: int | None = None,
        extra_notes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        messages = list(self.history)
        messages.insert(1, {"role": "system", "content": self.session.state_prompt()})
        insert_index = 2
        prior_transcript_prompt = self.session.prior_transcript_prompt()
        if prior_transcript_prompt:
            messages.insert(insert_index, {"role": "system", "content": prior_transcript_prompt})
            insert_index += 1
        memory_prompt = self.session.memory_prompt()
        if memory_prompt:
            messages.insert(insert_index, {"role": "system", "content": memory_prompt})
            insert_index += 1
        notes: list[str] = []
        if tool_budget_remaining is not None:
            notes.append(f"Tool budget remaining for this turn: {tool_budget_remaining}.")
        if extra_notes:
            notes.extend(extra_notes)
        if notes:
            messages.append({"role": "system", "content": "\n".join(notes)})
        return messages

    @staticmethod
    def _browser_sequence_note(user_text: str) -> str | None:
        text = user_text.strip()
        if not text:
            return None

        lower = text.lower()
        action_terms = [
            "打开",
            "访问",
            "进入",
            "搜索",
            "搜",
            "点击",
            "点一下",
            "输入",
            "提交",
            "open ",
            "navigate",
            "search ",
            "click ",
            "type ",
            "submit",
        ]
        page_terms = [
            "页面",
            "网页",
            "网站",
            "浏览器",
            "wikipedia",
            "github",
            "google",
            "x.com",
            "twitter.com",
            "http://",
            "https://",
        ]
        action_hits = sum(term in lower or term in text for term in action_terms)
        page_hits = sum(term in lower or term in text for term in page_terms)
        if action_hits < 2 and not (action_hits >= 1 and page_hits >= 1):
            return None

        return (
            "The user requested explicit browser interactions. Start from the user-requested site or page, "
            "then carry out the browser actions in order with browser_* tools. Do not shortcut to a guessed "
            "final URL or switch to web_search/web_fetch unless the browser path fails."
        )

    def _emit_tool_event(self, event: ToolExecutionEvent) -> None:
        if self.tool_event_handler is not None:
            self.tool_event_handler(event)

    def _emit_llm_usage(self, *, stage: str, output: Any) -> None:
        if self.llm_usage_handler is None or output.usage is None:
            return
        self.llm_usage_handler(
            LLMUsageEvent(
                usage=output.usage,
                stage=stage,
                tool_calls_requested=bool(output.tool_calls),
            )
        )

    @staticmethod
    def _clean_reply(text: str) -> str:
        if not text:
            return ""

        kept_lines: list[str] = []
        removed = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                kept_lines.append(line)
                continue
            try:
                parsed = json.loads(stripped)
            except Exception:
                kept_lines.append(line)
                continue
            if isinstance(parsed, dict) and (
                set(parsed.keys()) == {"ok"} or {"id", "json"}.issubset(parsed.keys())
            ):
                removed = True
                continue
            kept_lines.append(line)

        cleaned = "\n".join(kept_lines).strip()
        if removed and cleaned:
            return cleaned
        return text
