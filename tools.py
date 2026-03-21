from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from browser_runtime import BrowserHarness
from session import DEFAULT_MEMORY_MD, SessionState

ToolHandler = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[ToolSpec] | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools or []}

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def run(self, name: str, arguments: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Tool not found: {name}"

        try:
            parsed_args = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            return f"Invalid tool arguments: {exc}"

        if not isinstance(parsed_args, dict):
            return "Invalid tool arguments: expected a JSON object"

        try:
            return tool.handler(parsed_args)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _clip(text: str, limit: int = 12000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


_HTTP_USER_AGENT = "miniclaw/0.1"
_READ_FILE_PREFIX_RE = re.compile(r"^\s*\d+:\s")
_HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_MEMORY_SECTION_RE = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_MEMORY_ENTRY_RE = re.compile(r"^\s*-\s+(?P<key>[^:]+):\s*(?P<value>.*)$")
_TWEET_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/[^/]+/status/(?P<id>\d+)",
    re.IGNORECASE,
)
_DDG_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_RE = re.compile(
    r'class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.IGNORECASE | re.DOTALL,
)
_LIVE_BROWSER_HARNESSES: dict[str, BrowserHarness] = {}


class _VisibleTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lowered in {"p", "div", "section", "article", "main", "li", "br", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if lowered in {"p", "div", "section", "article", "main", "li", "br", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = raw.replace("\r", "\n")
        raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n")]
        kept = [line for line in lines if line]
        return "\n".join(kept).strip()


def _clean_html_fragment(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _decode_body(body: bytes, charset: str | None = None) -> str:
    candidates = [charset or "", "utf-8", "latin-1"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return body.decode(candidate, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def _http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: int = 15,
    max_bytes: int = 1_000_000,
) -> dict[str, Any]:
    request_headers = {
        "User-Agent": _HTTP_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.8",
    }
    if headers:
        request_headers.update(headers)

    request = urllib_request.Request(url, headers=request_headers)
    try:
        with urllib_request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read(max_bytes + 1)
            truncated = len(body) > max_bytes
            if truncated:
                body = body[:max_bytes]
            return {
                "url": response.geturl(),
                "status": getattr(response, "status", None) or response.getcode(),
                "content_type": response.headers.get("Content-Type", ""),
                "charset": response.headers.get_content_charset(),
                "body": body,
                "truncated": truncated,
            }
    except urllib_error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise ValueError(f"http error {exc.code} for {url}: {detail.strip() or exc.reason}") from exc
    except urllib_error.URLError as exc:
        raise ValueError(f"network error for {url}: {exc.reason}") from exc


def _extract_html_text(html_text: str) -> tuple[str | None, str]:
    title_match = _HTML_TITLE_RE.search(html_text)
    title = _clean_html_fragment(title_match.group(1)) if title_match else None
    parser = _VisibleTextHTMLParser()
    parser.feed(html_text)
    parser.close()
    return title, parser.text()


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = urllib_parse.urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com"):
        values = urllib_parse.parse_qs(parsed.query).get("uddg")
        if values:
            return urllib_parse.unquote(values[0])
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _parse_duckduckgo_results(html_text: str, *, count: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for match in _DDG_RESULT_LINK_RE.finditer(html_text):
        url = _unwrap_duckduckgo_url(match.group("href"))
        title = _clean_html_fragment(match.group("title"))
        tail = html_text[match.end() : match.end() + 1500]
        snippet_match = _DDG_SNIPPET_RE.search(tail)
        snippet = _clean_html_fragment(snippet_match.group("snippet")) if snippet_match else ""
        if not url or not title:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= count:
            break
    return results


def _resolve_twitter_cli_path(session: SessionState) -> Path:
    candidates: list[Path] = []
    env_path = os.getenv("MINICLAW_TWITTER_CLI_BIN", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    path_hit = shutil.which("twitter")
    if path_hit:
        candidates.append(Path(path_hit))

    candidates.append(session.resolve_path(".miniclaw/tmp/venv/bin/twitter"))

    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists() and resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved

    raise ValueError(
        "twitter-cli not found. Install it into .miniclaw/tmp/venv/bin/twitter, "
        "put `twitter` on PATH, or set MINICLAW_TWITTER_CLI_BIN."
    )


def _browser_runtime_key(session: SessionState) -> str:
    return session.session_id


def _browser_run_dir(session: SessionState) -> Path:
    root = (session.support_root() / "browser_runs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return (root / f"live-{session.session_id}").resolve()


def _default_browser_headless() -> bool:
    return os.getenv("MINICLAW_BROWSER_HEADLESS", "true").strip().lower() not in {"0", "false", "no"}


def _default_browser_timeout_ms() -> int:
    raw = os.getenv("MINICLAW_BROWSER_TIMEOUT_MS", "10000").strip()
    try:
        return max(1_000, min(120_000, int(raw)))
    except ValueError:
        return 10_000


def _get_live_browser_harness(session: SessionState, *, create: bool) -> BrowserHarness | None:
    key = _browser_runtime_key(session)
    harness = _LIVE_BROWSER_HARNESSES.get(key)
    if harness is not None or not create:
        return harness

    harness = BrowserHarness(
        _browser_run_dir(session),
        headless=_default_browser_headless(),
        timeout_ms=_default_browser_timeout_ms(),
    )
    _LIVE_BROWSER_HARNESSES[key] = harness
    return harness


def _observation_payload(session: SessionState, observation: Any) -> dict[str, Any]:
    data = observation.to_dict()
    run_dir = _browser_run_dir(session)
    data["run_dir"] = str(run_dir)
    data["current_url"] = data.get("post_url")
    return data


def _normalize_tweet_id(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("tweet_id is empty")
    if candidate.isdigit():
        return candidate
    match = _TWEET_URL_RE.search(candidate)
    if match:
        return match.group("id")
    raise ValueError("tweet_id must be a numeric tweet ID or a full tweet URL")


def _run_twitter_cli_json(
    session: SessionState,
    args: list[str],
    *,
    timeout_sec: int,
) -> tuple[Path, dict[str, Any]]:
    twitter_bin = _resolve_twitter_cli_path(session)
    proc = subprocess.run(
        [str(twitter_bin), *args, "--json"],
        cwd=session.workspace_root,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        detail = stderr or stdout or f"exit code {proc.returncode}"
        raise ValueError(f"twitter-cli failed: {detail}")
    if not stdout:
        raise ValueError("twitter-cli returned empty output")

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"twitter-cli returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("twitter-cli returned a non-object JSON payload")
    if parsed.get("ok") is False:
        raise ValueError(str(parsed.get("error") or "twitter-cli returned ok=false"))
    return twitter_bin, parsed


def _search_brave(query: str, *, count: int, timeout_sec: int) -> dict[str, Any] | None:
    api_key = os.getenv("BRAVE_API_KEY", "").strip() or os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        return None

    url = "https://api.search.brave.com/res/v1/web/search?" + urllib_parse.urlencode(
        {"q": query, "count": count}
    )
    response = _http_get(
        url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout_sec=timeout_sec,
    )
    data = json.loads(_decode_body(response["body"], response["charset"]))
    items = data.get("web", {}).get("results", [])
    results = [
        {
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "snippet": str(item.get("description") or ""),
        }
        for item in items[:count]
        if item.get("url") and item.get("title")
    ]
    return {"provider": "brave", "results": results}


def _search_duckduckgo(query: str, *, count: int, timeout_sec: int) -> dict[str, Any]:
    url = "https://html.duckduckgo.com/html/?" + urllib_parse.urlencode({"q": query})
    response = _http_get(url, timeout_sec=timeout_sec)
    html_text = _decode_body(response["body"], response["charset"])
    return {
        "provider": "duckduckgo_html",
        "results": _parse_duckduckgo_results(html_text, count=count),
    }


def _join_lines(lines: list[str], *, trailing_newline: bool) -> str:
    text = "\n".join(lines)
    if trailing_newline and (lines or text == ""):
        return f"{text}\n"
    return text


def _normalize_memory_label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_memory_value(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _canonical_memory_entry(key: str, value: str) -> str:
    cleaned_key = _normalize_memory_label(key)
    cleaned_value = _normalize_memory_value(value)
    if not cleaned_key:
        raise ValueError("memory key is empty")
    if not cleaned_value:
        raise ValueError("memory value is empty")
    return f"- {cleaned_key}: {cleaned_value}"


def _locate_memory_section(lines: list[str], section: str) -> tuple[int, int]:
    target = _normalize_memory_label(section).casefold()
    for index, line in enumerate(lines):
        match = _MEMORY_SECTION_RE.match(line.strip())
        if not match:
            continue
        if _normalize_memory_label(match.group("name")).casefold() != target:
            continue

        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if _MEMORY_SECTION_RE.match(lines[next_index].strip()):
                end = next_index
                break
        return index, end
    return -1, -1


def _ensure_memory_section(lines: list[str], section: str) -> tuple[int, int]:
    start, end = _locate_memory_section(lines, section)
    if start >= 0:
        return start, end

    heading = f"## {_normalize_memory_label(section)}"
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        lines.extend(DEFAULT_MEMORY_MD.rstrip("\n").splitlines())
        start, end = _locate_memory_section(lines, section)
        if start >= 0:
            return start, end

    lines.extend(["", heading, ""])
    return _locate_memory_section(lines, section)


def _replace_memory_entry(text: str, *, section: str, key: str, value: str) -> str:
    lines = text.splitlines() or DEFAULT_MEMORY_MD.rstrip("\n").splitlines()
    start, end = _ensure_memory_section(lines, section)
    entry_line = _canonical_memory_entry(key, value)
    target_key = _normalize_memory_label(key).casefold()

    for index in range(start + 1, end):
        match = _MEMORY_ENTRY_RE.match(lines[index])
        if match and _normalize_memory_label(match.group("key")).casefold() == target_key:
            lines[index] = entry_line
            return _join_lines(lines, trailing_newline=True)

    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, entry_line)
    return _join_lines(lines, trailing_newline=True)


def _forget_memory_entry(text: str, *, section: str, key: str) -> tuple[str, bool]:
    lines = text.splitlines()
    if not lines:
        return DEFAULT_MEMORY_MD, False

    start, end = _locate_memory_section(lines, section)
    if start < 0:
        return _join_lines(lines, trailing_newline=True), False

    target_key = _normalize_memory_label(key).casefold()
    for index in range(start + 1, end):
        match = _MEMORY_ENTRY_RE.match(lines[index])
        if match and _normalize_memory_label(match.group("key")).casefold() == target_key:
            del lines[index]
            while len(lines) >= 2:
                changed = False
                for blank_index in range(len(lines) - 1):
                    if not lines[blank_index].strip() and not lines[blank_index + 1].strip():
                        del lines[blank_index]
                        changed = True
                        break
                if not changed:
                    break
            return _join_lines(lines, trailing_newline=True), True

    return _join_lines(lines, trailing_newline=True), False


def _normalize_hunk_lines(hunk_lines: list[str]) -> list[str]:
    payloads = [line[1:] for line in hunk_lines if line]
    numbered_payloads = [payload for payload in payloads if payload.strip()]
    if not numbered_payloads:
        return hunk_lines
    if not all(_READ_FILE_PREFIX_RE.match(payload) for payload in numbered_payloads):
        return hunk_lines
    return [line[:1] + _READ_FILE_PREFIX_RE.sub("", line[1:], count=1) for line in hunk_lines]


def _find_block(lines: list[str], block: list[str], start: int) -> int:
    if not block:
        return start
    max_start = len(lines) - len(block)
    for index in range(max(start, 0), max_start + 1):
        if lines[index : index + len(block)] == block:
            return index
    return -1


def _apply_update_hunks(original_text: str, hunks: list[list[str]]) -> tuple[str, int]:
    lines = original_text.splitlines()
    trailing_newline = original_text.endswith("\n")
    cursor = 0
    changed_line_count = 0

    for raw_hunk in hunks:
        hunk = _normalize_hunk_lines(raw_hunk)
        old_block = [line[1:] for line in hunk if line[:1] in {" ", "-"}]
        new_block = [line[1:] for line in hunk if line[:1] in {" ", "+"}]
        if not old_block:
            raise ValueError("update hunks must include context or removed lines")

        start = _find_block(lines, old_block, cursor)
        if start < 0 and cursor > 0:
            start = _find_block(lines, old_block, 0)
        if start < 0:
            preview = "\\n".join(old_block[:6])
            raise ValueError(f"could not match patch hunk in file: {preview}")

        end = start + len(old_block)
        lines[start:end] = new_block
        cursor = start + len(new_block)
        changed_line_count += sum(1 for line in hunk if line[:1] in {"+", "-"})

    return _join_lines(lines, trailing_newline=trailing_newline), changed_line_count


def _parse_apply_patch(patch_text: str) -> list[dict[str, Any]]:
    lines = patch_text.splitlines()
    if not lines or lines[0].strip() != "*** Begin Patch":
        raise ValueError("patch must start with *** Begin Patch")

    operations: list[dict[str, Any]] = []
    index = 1
    while index < len(lines):
        line = lines[index]
        if line == "*** End Patch":
            if not operations:
                raise ValueError("patch has no operations")
            return operations

        if line.startswith("*** Update File: "):
            path = line.removeprefix("*** Update File: ").strip()
            if not path:
                raise ValueError("update file path is empty")

            index += 1
            if index < len(lines) and lines[index].startswith("*** Move to: "):
                raise ValueError("move operations are not supported")

            hunks: list[list[str]] = []
            current_hunk: list[str] = []
            saw_header = False
            while index < len(lines):
                current = lines[index]
                if current == "*** End of File":
                    index += 1
                    continue
                if current.startswith("*** "):
                    break
                if current.startswith("@@"):
                    saw_header = True
                    if current_hunk:
                        hunks.append(current_hunk)
                        current_hunk = []
                    index += 1
                    continue
                if not saw_header:
                    raise ValueError("update file patch is missing a @@ hunk header")
                if not current or current[:1] not in {" ", "+", "-"}:
                    raise ValueError(f"invalid patch line: {current}")
                current_hunk.append(current)
                index += 1

            if current_hunk:
                hunks.append(current_hunk)
            if not hunks:
                raise ValueError(f"update patch for {path} has no hunks")
            operations.append({"action": "update", "path": path, "hunks": hunks})
            continue

        if line.startswith("*** Add File: "):
            path = line.removeprefix("*** Add File: ").strip()
            if not path:
                raise ValueError("add file path is empty")

            index += 1
            content_lines: list[str] = []
            while index < len(lines):
                current = lines[index]
                if current.startswith("*** "):
                    break
                if not current.startswith("+"):
                    raise ValueError(f"invalid add file line: {current}")
                content_lines.append(current[1:])
                index += 1

            operations.append({"action": "add", "path": path, "content_lines": content_lines})
            continue

        if line.startswith("*** Delete File: "):
            path = line.removeprefix("*** Delete File: ").strip()
            if not path:
                raise ValueError("delete file path is empty")
            operations.append({"action": "delete", "path": path})
            index += 1
            continue

        raise ValueError(f"unknown patch directive: {line}")

    raise ValueError("patch is missing *** End Patch")


def _iter_entries(root: Path, max_depth: int) -> list[str]:
    entries: list[str] = []
    ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".miniclaw"}

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for child in children:
            if child.name in ignored:
                continue
            rel = child.relative_to(root)
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{rel}{suffix}")
            if child.is_dir():
                walk(child, depth + 1)

    walk(root, 0)
    return entries


def _build_set_workspace_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        path = session.set_workspace(str(args.get("path") or ""))
        return _json({"ok": True, "workspace_root": str(path)})

    return ToolSpec(
        name="set_workspace",
        description="Change the active workspace root to a directory path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative directory path.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_get_workspace_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        return _json({"ok": True, "workspace_root": str(session.workspace_root)})

    return ToolSpec(
        name="get_workspace",
        description="Return the current active workspace root.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_memory_read_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        max_chars = max(500, min(20_000, int(args.get("max_chars") or 6_000)))
        path = session.ensure_memory_file()
        content = path.read_text(encoding="utf-8")
        clipped, truncated = _clip(content, limit=max_chars)
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "content": clipped,
                "truncated": truncated,
            }
        )

    return ToolSpec(
        name="memory_read",
        description=(
            "Read the persistent Markdown memory file at .miniclaw/memory.md. "
            "Use this when you need to inspect or quote durable preferences, workspace rules, or stable facts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000, "default": 6000},
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_memory_replace_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        section = _normalize_memory_label(str(args.get("section") or ""))
        key = _normalize_memory_label(str(args.get("key") or ""))
        value = _normalize_memory_value(str(args.get("value") or ""))
        if not section:
            raise ValueError("section is empty")
        if not key:
            raise ValueError("key is empty")
        if not value:
            raise ValueError("value is empty")

        path = session.ensure_memory_file()
        previous = path.read_text(encoding="utf-8")
        updated = _replace_memory_entry(previous, section=section, key=key, value=value)
        path.write_text(updated, encoding="utf-8")
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "section": section,
                "key": key,
                "updated": previous != updated,
            }
        )

    return ToolSpec(
        name="memory_replace",
        description=(
            "Create or replace one durable memory entry inside .miniclaw/memory.md. "
            "Use this for current user preferences, workspace rules, or stable facts that should overwrite older values."
        ),
        parameters={
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Markdown section title, for example User Preferences."},
                "key": {"type": "string", "description": "Short stable label for the memory entry."},
                "value": {"type": "string", "description": "Current value to store for that label."},
            },
            "required": ["section", "key", "value"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_memory_forget_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        section = _normalize_memory_label(str(args.get("section") or ""))
        key = _normalize_memory_label(str(args.get("key") or ""))
        if not section:
            raise ValueError("section is empty")
        if not key:
            raise ValueError("key is empty")

        path = session.ensure_memory_file()
        previous = path.read_text(encoding="utf-8")
        updated, removed = _forget_memory_entry(previous, section=section, key=key)
        path.write_text(updated, encoding="utf-8")
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "section": section,
                "key": key,
                "removed": removed,
            }
        )

    return ToolSpec(
        name="memory_forget",
        description=(
            "Remove one durable memory entry from .miniclaw/memory.md when it is no longer true or the user asks to forget it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Markdown section title, for example User Preferences."},
                "key": {"type": "string", "description": "Short stable label for the memory entry to remove."},
            },
            "required": ["section", "key"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_twitter_whoami_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        timeout_sec = max(1, min(120, int(args.get("timeout_sec") or 30)))
        twitter_bin, parsed = _run_twitter_cli_json(session, ["whoami"], timeout_sec=timeout_sec)
        user = parsed.get("data", {}).get("user") if isinstance(parsed.get("data"), dict) else None
        return _json(
            {
                "ok": True,
                "cli_path": str(twitter_bin),
                "authenticated": bool(user),
                "user": user,
            }
        )

    return ToolSpec(
        name="twitter_whoami",
        description=(
            "Return the currently authenticated Twitter/X account using twitter-cli. "
            "Use this to confirm login status before relying on Twitter-specific tools."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 120, "default": 30},
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_twitter_user_posts_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        screen_name = str(args.get("screen_name") or "").strip().lstrip("@")
        if not screen_name:
            raise ValueError("screen_name is empty")

        max_items = max(1, min(20, int(args.get("max_items") or 10)))
        timeout_sec = max(1, min(120, int(args.get("timeout_sec") or 45)))
        twitter_bin, parsed = _run_twitter_cli_json(
            session,
            ["user-posts", screen_name, "--max", str(max_items)],
            timeout_sec=timeout_sec,
        )
        posts = parsed.get("data")
        if not isinstance(posts, list):
            raise ValueError("twitter-cli returned an unexpected user-posts payload")
        return _json(
            {
                "ok": True,
                "cli_path": str(twitter_bin),
                "screen_name": screen_name,
                "count": len(posts),
                "posts": posts,
            }
        )

    return ToolSpec(
        name="twitter_user_posts",
        description=(
            "Fetch recent tweets from a Twitter/X user via twitter-cli. "
            "Prefer this over web_search/web_fetch when the user explicitly wants recent tweets from a known account."
        ),
        parameters={
            "type": "object",
            "properties": {
                "screen_name": {"type": "string", "description": "Twitter/X handle without the @ prefix."},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 120, "default": 45},
            },
            "required": ["screen_name"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_twitter_tweet_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        tweet_id = _normalize_tweet_id(str(args.get("tweet_id") or ""))

        max_replies = max(0, min(20, int(args.get("max_replies") or 5)))
        timeout_sec = max(1, min(120, int(args.get("timeout_sec") or 45)))
        twitter_bin, parsed = _run_twitter_cli_json(
            session,
            ["tweet", tweet_id, "--max", str(max_replies)],
            timeout_sec=timeout_sec,
        )
        items = parsed.get("data")
        if not isinstance(items, list):
            raise ValueError("twitter-cli returned an unexpected tweet payload")
        return _json(
            {
                "ok": True,
                "cli_path": str(twitter_bin),
                "tweet_id": tweet_id,
                "count": len(items),
                "items": items,
            }
        )

    return ToolSpec(
        name="twitter_tweet",
        description=(
            "Fetch a specific tweet and a small number of replies via twitter-cli. "
            "Use this when the user references a tweet ID/URL or wants direct tweet details."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tweet_id": {"type": "string", "description": "Numeric tweet ID or full tweet URL."},
                "max_replies": {"type": "integer", "minimum": 0, "maximum": 20, "default": 5},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 120, "default": 45},
            },
            "required": ["tweet_id"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_browser_navigate_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url is empty")
        harness = _get_live_browser_harness(session, create=True)
        if harness is None:
            raise ValueError("browser harness could not be created")
        observation = harness.navigate(url)
        return _json(_observation_payload(session, observation))

    return ToolSpec(
        name="browser_navigate",
        description=(
            "Open a URL in a real browser session and return a structured page observation. "
            "Use this for interactive or dynamic pages where web_fetch is insufficient. "
            "When the user names a site to open first, navigate to that starting page instead of guessing a later destination."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http/https URL to open in the browser."},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_browser_snapshot_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        del args
        harness = _get_live_browser_harness(session, create=False)
        if harness is None:
            raise ValueError("browser is not active; call browser_navigate first")
        observation = harness.snapshot()
        return _json(_observation_payload(session, observation))

    return ToolSpec(
        name="browser_snapshot",
        description="Capture the current browser page state without changing it.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_browser_act_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        action = str(args.get("action") or "").strip()
        target = str(args.get("target") or "").strip()
        value = args.get("value")
        if not action:
            raise ValueError("action is empty")
        if not target:
            raise ValueError("target is empty")
        harness = _get_live_browser_harness(session, create=False)
        if harness is None:
            raise ValueError("browser is not active; call browser_navigate first")
        observation = harness.act(action, target, None if value is None else str(value))
        return _json(_observation_payload(session, observation))

    return ToolSpec(
        name="browser_act",
        description=(
            "Perform one browser action against the current page. "
            "Supported actions are click, type, press, and wait."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "type", "press", "wait"],
                    "description": "Action to perform on the current page.",
                },
                "target": {
                    "type": "string",
                    "description": "CSS selector or stable selector hint such as a data-testid selector.",
                },
                "value": {
                    "type": "string",
                    "description": "Optional text value for type/press/wait actions.",
                },
            },
            "required": ["action", "target"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_browser_extract_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        kind = str(args.get("kind") or "text").strip()
        harness = _get_live_browser_harness(session, create=False)
        if harness is None:
            raise ValueError("browser is not active; call browser_navigate first")
        observation = harness.extract(kind)
        return _json(_observation_payload(session, observation))

    return ToolSpec(
        name="browser_extract",
        description=(
            "Extract structured content from the current browser page. "
            "Phase 1 supports text and list extraction. "
            "Prefer this over web_fetch when the relevant content is already open in the live browser session."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["text", "list"],
                    "default": "text",
                    "description": "Extraction mode for the current page.",
                },
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_browser_close_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        del args
        key = _browser_runtime_key(session)
        harness = _LIVE_BROWSER_HARNESSES.pop(key, None)
        if harness is None:
            return _json({"ok": True, "closed": False, "run_dir": str(_browser_run_dir(session))})
        steps = harness.step_index
        run_dir = str(harness.run_dir)
        harness.close()
        return _json({"ok": True, "closed": True, "steps_recorded": steps, "run_dir": run_dir})

    return ToolSpec(
        name="browser_close",
        description="Close the current browser session and keep its artifacts on disk.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_list_files_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        path = session.resolve_path(str(args.get("path") or "."))
        max_depth = int(args.get("max_depth") or 2)
        max_entries = int(args.get("max_entries") or 200)
        if not path.exists():
            raise ValueError(f"path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"path is not a directory: {path}")

        entries = _iter_entries(path, max_depth=max_depth)
        truncated = len(entries) > max_entries
        if truncated:
            entries = entries[:max_entries]

        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "entries": entries,
                "truncated": truncated,
            }
        )

    return ToolSpec(
        name="list_files",
        description="List files and directories inside the current workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to the workspace."},
                "max_depth": {"type": "integer", "minimum": 0, "maximum": 6, "default": 2},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_read_file_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        path = session.resolve_path(str(args.get("path") or ""))
        start_line = max(1, int(args.get("start_line") or 1))
        max_lines = max(1, min(400, int(args.get("max_lines") or 200)))
        if not path.exists():
            raise ValueError(f"file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"path is not a file: {path}")

        lines = path.read_text(encoding="utf-8").splitlines()
        start_idx = start_line - 1
        end_idx = min(len(lines), start_idx + max_lines)
        numbered = "\n".join(f"{i + 1:>4}: {line}" for i, line in enumerate(lines[start_idx:end_idx], start=start_idx))
        clipped, truncated = _clip(numbered, limit=16000)
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "start_line": start_line,
                "end_line": end_idx,
                "content": clipped,
                "truncated": truncated,
            }
        )

    return ToolSpec(
        name="read_file",
        description="Read a text file inside the current workspace with line numbers.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "start_line": {"type": "integer", "minimum": 1, "default": 1},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": 400, "default": 200},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_search_text_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is empty")

        base = session.resolve_path(str(args.get("path") or "."))
        if not base.exists():
            raise ValueError(f"path does not exist: {base}")

        ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".miniclaw"}
        matches: list[str] = []
        max_results = max(1, min(200, int(args.get("max_results") or 50)))

        for candidate in sorted(base.rglob("*")):
            if any(part in ignored for part in candidate.parts):
                continue
            if not candidate.is_file():
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = candidate.relative_to(session.workspace_root)
            for index, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(f"{rel}:{index}: {line.strip()}")
                    if len(matches) >= max_results:
                        return _json({"ok": True, "matches": matches, "truncated": True})

        return _json({"ok": True, "matches": matches, "truncated": False})

    return ToolSpec(
        name="search_text",
        description="Search for plain text inside workspace files.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Plain text to search for."},
                "path": {"type": "string", "description": "Optional subdirectory or file path."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _is_textual_content_type(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return (
        lowered.startswith("text/")
        or "json" in lowered
        or "xml" in lowered
        or "javascript" in lowered
        or "html" in lowered
    )


def _build_web_search_tool() -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is empty")

        count = max(1, min(10, int(args.get("count") or 5)))
        timeout_sec = max(1, min(30, int(args.get("timeout_sec") or 15)))
        search_result = _search_brave(query, count=count, timeout_sec=timeout_sec)
        if search_result is None:
            search_result = _search_duckduckgo(query, count=count, timeout_sec=timeout_sec)

        return _json(
            {
                "ok": True,
                "query": query,
                "provider": search_result["provider"],
                "results": search_result["results"],
            }
        )

    return ToolSpec(
        name="web_search",
        description=(
            "Search the public web for external information. "
            "Use this when the user asks for current facts or information outside the workspace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 30, "default": 15},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_web_fetch_tool() -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        raw_url = str(args.get("url") or "").strip()
        if not raw_url:
            raise ValueError("url is empty")

        parsed = urllib_parse.urlparse(raw_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported url scheme: {parsed.scheme or '(missing)'}")

        timeout_sec = max(1, min(30, int(args.get("timeout_sec") or 15)))
        max_chars = max(500, min(20_000, int(args.get("max_chars") or 8_000)))
        response = _http_get(
            raw_url,
            headers={"Accept": "text/html, text/plain, application/json;q=0.9, */*;q=0.1"},
            timeout_sec=timeout_sec,
            max_bytes=1_000_000,
        )

        content_type = str(response["content_type"] or "")
        if not _is_textual_content_type(content_type):
            raise ValueError(f"unsupported content type: {content_type or 'unknown'}")

        decoded = _decode_body(response["body"], response["charset"])
        title: str | None = None
        text = decoded
        if "html" in content_type.lower():
            title, text = _extract_html_text(decoded)

        clipped_text, truncated = _clip(text, limit=max_chars)
        return _json(
            {
                "ok": True,
                "url": response["url"],
                "status": response["status"],
                "content_type": content_type,
                "title": title,
                "text": clipped_text,
                "truncated": truncated or bool(response["truncated"]),
            }
        )

    return ToolSpec(
        name="web_fetch",
        description=(
            "Fetch and extract readable text from a public URL. "
            "Use this after web_search when you need to inspect a specific result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTP or HTTPS URL to fetch."},
                "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000, "default": 8000},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 30, "default": 15},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_write_file_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        path = session.resolve_path(str(args.get("path") or ""))
        content = str(args.get("content") or "")
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "bytes_written": len(content.encode("utf-8")),
            }
        )

    return ToolSpec(
        name="write_file",
        description=(
            "Write or overwrite a text file inside the current workspace. "
            "Use this for intentional project file changes, not scratch scripts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "content": {"type": "string", "description": "Full file contents to write."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_apply_patch_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        patch_text = str(args.get("patch") or "")
        if not patch_text.strip():
            raise ValueError("patch is empty")

        operations = _parse_apply_patch(patch_text)
        applied: list[dict[str, Any]] = []
        for operation in operations:
            path = session.resolve_path(str(operation["path"]))
            action = str(operation["action"])

            if action == "update":
                if not path.exists():
                    raise ValueError(f"file does not exist: {path}")
                if not path.is_file():
                    raise ValueError(f"path is not a file: {path}")
                original = path.read_text(encoding="utf-8")
                updated, changed_line_count = _apply_update_hunks(original, operation["hunks"])
                path.write_text(updated, encoding="utf-8")
                applied.append(
                    {
                        "action": action,
                        "path": str(path.relative_to(session.workspace_root)),
                        "changed_lines": changed_line_count,
                    }
                )
                continue

            if action == "add":
                if path.exists():
                    raise ValueError(f"file already exists: {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                content_lines = [str(line) for line in operation["content_lines"]]
                content = _join_lines(content_lines, trailing_newline=bool(content_lines))
                path.write_text(content, encoding="utf-8")
                applied.append(
                    {
                        "action": action,
                        "path": str(path.relative_to(session.workspace_root)),
                        "bytes_written": len(content.encode("utf-8")),
                    }
                )
                continue

            if action == "delete":
                if not path.exists():
                    raise ValueError(f"file does not exist: {path}")
                if not path.is_file():
                    raise ValueError(f"path is not a file: {path}")
                path.unlink()
                applied.append({"action": action, "path": str(path.relative_to(session.workspace_root))})
                continue

            raise ValueError(f"unsupported patch action: {action}")

        return _json({"ok": True, "operations": applied, "files_changed": len(applied)})

    return ToolSpec(
        name="apply_patch",
        description=(
            "Apply a structured patch inside the workspace. Prefer this for editing existing files. "
            "Patch format: *** Begin Patch, then one or more *** Update File:, *** Add File:, or "
            "*** Delete File: blocks, and finally *** End Patch. Update blocks must contain @@ lines "
            "followed by context (space), removals (-), and additions (+). Use raw file text, not the "
            "line-number prefixes from read_file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "Structured patch text to apply inside the current workspace.",
                }
            },
            "required": ["patch"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_write_temp_file_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        content = str(args.get("content") or "")
        filename = str(args.get("filename") or "").strip() or None
        suffix = str(args.get("suffix") or ".tmp").strip() or ".tmp"
        path = session.make_temp_path(filename, suffix=suffix)
        path.write_text(content, encoding="utf-8")
        return _json(
            {
                "ok": True,
                "path": str(path.relative_to(session.workspace_root)),
                "bytes_written": len(content.encode("utf-8")),
            }
        )

    return ToolSpec(
        name="write_temp_file",
        description=(
            "Write a temporary file under .miniclaw/tmp inside the workspace. "
            "Prefer this for scratch scripts and temporary artifacts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full contents of the temporary file."},
                "filename": {"type": "string", "description": "Optional basename for the temporary file."},
                "suffix": {"type": "string", "description": "Optional suffix when filename is omitted.", "default": ".tmp"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _is_blocked_command(command: str) -> str | None:
    text = command.strip().lower()
    blocked_markers = (
        "rm -rf /",
        "sudo ",
        "shutdown",
        "reboot",
        "mkfs",
        "dd ",
        "diskutil erase",
        "git reset --hard",
        "git clean -fd",
    )
    for marker in blocked_markers:
        if marker in text:
            return marker
    if any(token in command for token in ("&&", "||", ";", "|", ">", "<", "$(", "`")):
        return "shell operators are not allowed"
    return None


def _build_run_command_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        command = str(args.get("command") or "").strip()
        if not command:
            raise ValueError("command is empty")

        blocked = _is_blocked_command(command)
        if blocked:
            raise ValueError(f"blocked command pattern: {blocked}")

        cwd = session.resolve_path(str(args.get("cwd") or "."))
        if not cwd.is_dir():
            raise ValueError(f"cwd is not a directory: {cwd}")

        timeout_sec = max(1, min(120, int(args.get("timeout_sec") or 20)))
        proc = subprocess.run(
            shlex.split(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        stdout, stdout_truncated = _clip(proc.stdout)
        stderr, stderr_truncated = _clip(proc.stderr)

        return _json(
            {
                "ok": proc.returncode == 0,
                "command": command,
                "cwd": str(cwd.relative_to(session.workspace_root)),
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
        )

    return ToolSpec(
        name="run_command",
        description=(
            "Run a simple non-shell command inside the current workspace. "
            "Do not use shell operators, pipes, redirects, or chained commands."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Simple command to execute."},
                "cwd": {"type": "string", "description": "Optional working directory relative to the workspace."},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 120, "default": 20},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _build_run_python_tool(session: SessionState) -> ToolSpec:
    def handler(args: dict[str, Any]) -> str:
        code = str(args.get("code") or "")
        if not code.strip():
            raise ValueError("code is empty")

        cwd = session.resolve_path(str(args.get("cwd") or "."))
        if not cwd.is_dir():
            raise ValueError(f"cwd is not a directory: {cwd}")

        timeout_sec = max(1, min(120, int(args.get("timeout_sec") or 20)))
        proc = subprocess.run(
            ["python3", "-"],
            cwd=cwd,
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        stdout, stdout_truncated = _clip(proc.stdout)
        stderr, stderr_truncated = _clip(proc.stderr)

        return _json(
            {
                "ok": proc.returncode == 0,
                "cwd": str(cwd.relative_to(session.workspace_root)),
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
        )

    return ToolSpec(
        name="run_python",
        description=(
            "Run a short Python program directly without writing a file. "
            "Prefer this for calculations, quick validation, and one-off scripts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code to execute."},
                "cwd": {"type": "string", "description": "Optional working directory relative to the workspace."},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 120, "default": 20},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def build_default_registry(session: SessionState) -> ToolRegistry:
    return ToolRegistry(
        [
            _build_set_workspace_tool(session),
            _build_get_workspace_tool(session),
            _build_memory_read_tool(session),
            _build_memory_replace_tool(session),
            _build_memory_forget_tool(session),
            _build_twitter_whoami_tool(session),
            _build_twitter_user_posts_tool(session),
            _build_twitter_tweet_tool(session),
            _build_list_files_tool(session),
            _build_read_file_tool(session),
            _build_search_text_tool(session),
            _build_web_search_tool(),
            _build_web_fetch_tool(),
            _build_browser_navigate_tool(session),
            _build_browser_snapshot_tool(session),
            _build_browser_act_tool(session),
            _build_browser_extract_tool(session),
            _build_browser_close_tool(session),
            _build_apply_patch_tool(session),
            _build_write_file_tool(session),
            _build_write_temp_file_tool(session),
            _build_run_command_tool(session),
            _build_run_python_tool(session),
        ]
    )
