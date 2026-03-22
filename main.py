from __future__ import annotations

import argparse
import json
import select
import sys
from typing import Any, TextIO

from agent import Agent, DEFAULT_SYSTEM_PROMPT, LLMUsageEvent, ToolExecutionEvent
from llm import DEFAULT_MODEL, LLMClient
from session import SessionState
from tools import build_default_registry

try:
    from rich import box
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.markup import escape
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover - optional UI dependency
    box = None
    Console = None
    Markdown = None
    Panel = None
    Table = None
    Text = None
    RICH_AVAILABLE = False


# Keep a short linger after each submitted line so desktop terminal paste bursts
# with slight inter-line jitter still arrive as one logical message.
PASTE_WINDOW_SEC = 0.2
CONSOLE = Console(highlight=False, soft_wrap=True) if RICH_AVAILABLE else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="miniclaw: minimal CLI agent")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name to use")
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="Override the default system prompt for this session",
    )
    return parser


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clip(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def _escape(text: str) -> str:
    if RICH_AVAILABLE:
        return escape(text)
    return text


def _summarize_patch_text(patch_text: str) -> str:
    operations: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("*** Update File: "):
            operations.append(f"update:{line.removeprefix('*** Update File: ').strip()}")
        elif line.startswith("*** Add File: "):
            operations.append(f"add:{line.removeprefix('*** Add File: ').strip()}")
        elif line.startswith("*** Delete File: "):
            operations.append(f"delete:{line.removeprefix('*** Delete File: ').strip()}")

    if not operations:
        return f"lines={len(patch_text.splitlines())}"

    preview = ", ".join(operations[:3])
    if len(operations) > 3:
        preview += ", ..."
    return f"ops={len(operations)} {preview}"


def _summarize_tool_arguments(tool_name: str, raw_arguments: str) -> str:
    args = _parse_json_object(raw_arguments)
    if args is None:
        return _clip(raw_arguments.strip() or "{}")

    if tool_name == "set_workspace":
        return f"path={args.get('path', '')}"
    if tool_name == "memory_read":
        return f"max_chars={args.get('max_chars', 6000)}"
    if tool_name == "memory_replace":
        return f"section={args.get('section', '')!r} key={args.get('key', '')!r}"
    if tool_name == "memory_forget":
        return f"section={args.get('section', '')!r} key={args.get('key', '')!r}"
    if tool_name == "twitter_whoami":
        return f"timeout={args.get('timeout_sec', 30)}"
    if tool_name == "twitter_user_posts":
        return f"screen_name={args.get('screen_name', '')!r} max={args.get('max_items', 10)}"
    if tool_name == "twitter_tweet":
        return f"tweet_id={args.get('tweet_id', '')!r} replies={args.get('max_replies', 5)}"
    if tool_name == "browser_navigate":
        return f"url={args.get('url', '')}"
    if tool_name == "browser_snapshot":
        return "(current page)"
    if tool_name == "browser_act":
        action = args.get("action", "")
        target = args.get("target", "")
        value = args.get("value", "")
        suffix = f" value={value!r}" if value else ""
        return f"action={action!r} target={target!r}{suffix}"
    if tool_name == "browser_extract":
        return f"kind={args.get('kind', 'text')!r}"
    if tool_name == "browser_close":
        return "(close session)"
    if tool_name == "list_files":
        return f"path={args.get('path', '.')} depth={args.get('max_depth', 2)}"
    if tool_name == "read_file":
        return f"path={args.get('path', '')} start={args.get('start_line', 1)} lines={args.get('max_lines', 200)}"
    if tool_name == "search_text":
        return f"query={args.get('query', '')!r} path={args.get('path', '.')}"
    if tool_name == "web_search":
        return f"query={args.get('query', '')!r} count={args.get('count', 5)}"
    if tool_name == "web_fetch":
        return f"url={args.get('url', '')} max_chars={args.get('max_chars', 8000)}"
    if tool_name == "apply_patch":
        return _summarize_patch_text(str(args.get("patch", "")))
    if tool_name == "write_file":
        content = str(args.get("content", ""))
        return f"path={args.get('path', '')} bytes={len(content.encode('utf-8'))}"
    if tool_name == "write_temp_file":
        content = str(args.get("content", ""))
        filename = args.get("filename", "")
        return f"filename={filename!r} bytes={len(content.encode('utf-8'))}"
    if tool_name == "run_command":
        cwd = args.get("cwd", ".")
        return f"command={args.get('command', '')!r} cwd={cwd}"
    if tool_name == "run_python":
        cwd = args.get("cwd", ".")
        code = str(args.get("code", ""))
        lines = len(code.splitlines()) if code else 0
        return f"cwd={cwd} lines={lines}"

    return _clip(json.dumps(args, ensure_ascii=False))


def _summarize_tool_result(tool_name: str, raw_result: str) -> str:
    result = _parse_json_object(raw_result)
    if result is None:
        return _clip(raw_result.strip() or "(empty)")

    if tool_name in {"set_workspace", "get_workspace"}:
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"workspace={result.get('workspace_root', '')}"
    if tool_name == "memory_read":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        suffix = " truncated" if result.get("truncated") else ""
        return f"path={result.get('path', '')}{suffix}"
    if tool_name == "memory_replace":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"section={result.get('section', '')!r} key={result.get('key', '')!r}"
    if tool_name == "memory_forget":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        status = "removed" if result.get("removed") else "missing"
        return f"section={result.get('section', '')!r} key={result.get('key', '')!r} {status}"
    if tool_name == "twitter_whoami":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        handle = user.get("screen_name") or user.get("legacy", {}).get("screen_name") or "?"
        return f"authenticated={result.get('authenticated', False)} user={handle!r}"
    if tool_name == "twitter_user_posts":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"screen_name={result.get('screen_name', '')!r} count={result.get('count', '?')}"
    if tool_name == "twitter_tweet":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"tweet_id={result.get('tweet_id', '')!r} count={result.get('count', '?')}"
    if tool_name == "browser_navigate":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"step={result.get('step_index', '?')} url={result.get('current_url', '')} title={result.get('title', '')!r}"
    if tool_name == "browser_snapshot":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"step={result.get('step_index', '?')} url={result.get('current_url', '')} title={result.get('title', '')!r}"
    if tool_name == "browser_act":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        normalized = result.get("normalized_action", {})
        action = normalized.get("action", "?") if isinstance(normalized, dict) else "?"
        return f"step={result.get('step_index', '?')} action={action!r} url={result.get('current_url', '')}"
    if tool_name == "browser_extract":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        extracted = result.get("extracted", {})
        kind = extracted.get("kind", "?") if isinstance(extracted, dict) else "?"
        value = extracted.get("value", "") if isinstance(extracted, dict) else ""
        size = len(value) if isinstance(value, list) else len(str(value))
        return f"step={result.get('step_index', '?')} kind={kind!r} size={size}"
    if tool_name == "browser_close":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"closed={result.get('closed', False)} steps={result.get('steps_recorded', 0)}"
    if tool_name == "list_files":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        entries = result.get("entries", [])
        count = len(entries) if isinstance(entries, list) else "?"
        suffix = " truncated" if result.get("truncated") else ""
        return f"path={result.get('path', '.')} entries={count}{suffix}"
    if tool_name == "read_file":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"path={result.get('path', '')} lines={result.get('start_line', '?')}-{result.get('end_line', '?')}"
    if tool_name == "search_text":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        matches = result.get("matches", [])
        count = len(matches) if isinstance(matches, list) else "?"
        suffix = " truncated" if result.get("truncated") else ""
        return f"matches={count}{suffix}"
    if tool_name == "web_search":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        results = result.get("results", [])
        count = len(results) if isinstance(results, list) else "?"
        return f"provider={result.get('provider', '?')} results={count}"
    if tool_name == "web_fetch":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        text = str(result.get("text", "")).strip()
        summary = f"status={result.get('status', '?')} type={result.get('content_type', '?')}"
        if text:
            summary += f" text={_clip(text.splitlines()[0])!r}"
        return summary
    if tool_name == "apply_patch":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        operations = result.get("operations", [])
        if not isinstance(operations, list):
            return f"files={result.get('files_changed', '?')}"
        summary_parts = [
            f"{item.get('action', '?')}:{item.get('path', '?')}"
            for item in operations[:3]
            if isinstance(item, dict)
        ]
        preview = ", ".join(summary_parts)
        if len(operations) > 3:
            preview = f"{preview}, ..." if preview else "..."
        return f"files={result.get('files_changed', len(operations))} {preview}".strip()
    if tool_name == "write_file":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"path={result.get('path', '')} bytes={result.get('bytes_written', '?')}"
    if tool_name == "write_temp_file":
        if result.get("ok") is False:
            return f"error={result.get('error', 'unknown error')}"
        return f"path={result.get('path', '')} bytes={result.get('bytes_written', '?')}"
    if tool_name == "run_command":
        summary = f"exit={result.get('exit_code', '?')} cwd={result.get('cwd', '.')}"
        stdout = str(result.get("stdout", "")).strip()
        stderr = str(result.get("stderr", "")).strip()
        if stdout:
            summary += f" stdout={_clip(stdout.splitlines()[0])!r}"
        elif stderr:
            summary += f" stderr={_clip(stderr.splitlines()[0])!r}"
        return summary
    if tool_name == "run_python":
        summary = f"exit={result.get('exit_code', '?')} cwd={result.get('cwd', '.')}"
        stdout = str(result.get("stdout", "")).strip()
        stderr = str(result.get("stderr", "")).strip()
        if stdout:
            summary += f" stdout={_clip(stdout.splitlines()[0])!r}"
        elif stderr:
            summary += f" stderr={_clip(stderr.splitlines()[0])!r}"
        return summary

    return _clip(json.dumps(result, ensure_ascii=False))


def _print_tool_event(event: ToolExecutionEvent) -> None:
    if event.phase == "start":
        summary = _summarize_tool_arguments(event.tool_name, event.arguments)
        if CONSOLE is not None:
            CONSOLE.print(
                Text.assemble(
                    ("tool", "bold cyan"),
                    ("  ", ""),
                    (event.tool_name, "cyan"),
                    ("  ", ""),
                    (_escape(summary), "dim"),
                )
            )
        else:
            print(f"[tool] {event.tool_name} {summary}")
    elif event.phase == "finish":
        summary = _summarize_tool_result(event.tool_name, event.result or "")
        is_error = summary.startswith("error=")
        if CONSOLE is not None:
            CONSOLE.print(
                Text.assemble(
                    ("tool", "bold red" if is_error else "bold green"),
                    ("  ", ""),
                    (event.tool_name, "red" if is_error else "green"),
                    ("  ", ""),
                    (_escape(summary), "red" if is_error else "dim"),
                )
            )
        else:
            print(f"[tool-result] {event.tool_name} {summary}")


def _print_llm_usage(event: LLMUsageEvent) -> None:
    usage = event.usage
    parts = [f"stage={event.stage}"]
    if usage.prompt_tokens is not None:
        parts.append(f"prompt={usage.prompt_tokens}")
    if usage.completion_tokens is not None:
        parts.append(f"completion={usage.completion_tokens}")
    if usage.total_tokens is not None:
        parts.append(f"total={usage.total_tokens}")
    if usage.cached_tokens is not None:
        parts.append(f"cached={usage.cached_tokens}")
    if event.tool_calls_requested:
        parts.append("tool_calls=yes")
    summary = " ".join(parts)
    if CONSOLE is not None:
        CONSOLE.print(Text.assemble(("llm", "bold magenta"), ("  ", ""), (summary, "dim")))
    else:
        print(f"[llm] {summary}")


def _print_prompt() -> None:
    if CONSOLE is not None:
        CONSOLE.print(Text.assemble(("You", "bold bright_cyan"), (" > ", "bold bright_cyan")), end="")
    else:
        print("> ", end="", flush=True)


def _interactive_prompt_text() -> str:
    return "You > "


def _print_welcome(session: SessionState, model: str) -> None:
    if CONSOLE is None:
        print(f"miniclaw ready ({model}). Workspace: {session.workspace_root}")
        if session.resume_transcript_path is not None:
            print(f"Recent transcript: {session.resume_transcript_path}")
        print("Type 'exit' or 'quit' to leave.")
        return

    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Model", model)
    grid.add_row("Workspace", str(session.workspace_root))
    if session.resume_transcript_path is not None:
        grid.add_row("Recent", str(session.resume_transcript_path))
    grid.add_row("Exit", "Type 'exit' or 'quit' to leave.")
    CONSOLE.print(
        Panel(
            grid,
            title="miniclaw",
            title_align="left",
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


def _print_interrupt() -> None:
    if CONSOLE is not None:
        CONSOLE.print(Text("Interrupted.", style="bold yellow"))
    else:
        print("\nInterrupted.")


def _print_error(message: str) -> None:
    if CONSOLE is not None:
        CONSOLE.print(Text.assemble(("error", "bold red"), ("  ", ""), (_escape(message), "red")))
    else:
        print(f"error: {message}", file=sys.stderr)


def _print_reply(reply: str) -> None:
    if CONSOLE is not None and Markdown is not None and Panel is not None:
        CONSOLE.print()
        CONSOLE.print(
            Panel(
                Markdown(reply, code_theme="monokai"),
                title="Claw",
                title_align="left",
                border_style="white",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        CONSOLE.print()
        return

    print(reply)


def _supports_paste_coalescing(stream: TextIO) -> bool:
    try:
        return stream.isatty() and stream.fileno() >= 0
    except Exception:
        return False


def _read_user_text(stream: TextIO, *, paste_window_sec: float = PASTE_WINDOW_SEC) -> str | None:
    # Use Python's normal interactive line editing on the real TTY stdin.
    # This keeps IME/backspace handling stable for CJK input while still
    # allowing us to drain additional pasted lines afterwards.
    if stream is sys.stdin and _supports_paste_coalescing(stream):
        try:
            first_line = input(_interactive_prompt_text())
        except EOFError:
            return None
        lines = [first_line]
    else:
        _print_prompt()
        first_line = stream.readline()
        if first_line == "":
            return None
        lines = [first_line.rstrip("\n")]
        if not _supports_paste_coalescing(stream):
            return "\n".join(lines).strip()

    while True:
        ready, _, _ = select.select([stream], [], [], paste_window_sec)
        if not ready:
            break
        next_line = stream.readline()
        if next_line == "":
            break
        lines.append(next_line.rstrip("\n"))

    return "\n".join(lines).strip()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    session = SessionState.from_cwd()
    llm = LLMClient(model=args.model)
    agent = Agent(
        llm,
        session,
        build_default_registry(session),
        system_prompt=args.system_prompt or DEFAULT_SYSTEM_PROMPT,
        tool_event_handler=_print_tool_event,
        llm_usage_handler=_print_llm_usage,
    )

    _print_welcome(session, llm.model)

    while True:
        try:
            user_text = _read_user_text(sys.stdin)
        except KeyboardInterrupt:
            if CONSOLE is not None:
                CONSOLE.print()
            _print_interrupt()
            return 130

        if user_text is None:
            if CONSOLE is not None:
                CONSOLE.print()
            else:
                print()
            return 0

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            return 0

        try:
            reply = agent.run_turn(user_text)
        except Exception as exc:
            _print_error(str(exc))
            continue

        _print_reply(reply)


if __name__ == "__main__":
    raise SystemExit(main())
