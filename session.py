from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import uuid

DEFAULT_MEMORY_MD = """# Memory

## User Preferences

## Workspace Rules

## Stable Facts
"""


@dataclass
class SessionState:
    workspace_root: Path
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    session_started_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    )
    transcript_path: Path = field(init=False)
    resume_transcript_path: Path | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.workspace_root = self.workspace_root.resolve()
        self.resume_transcript_path = self._latest_session_path()
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        self.transcript_path = (self.sessions_root() / f"{timestamp}-{self.session_id}.jsonl").resolve()

    @classmethod
    def from_cwd(cls) -> "SessionState":
        return cls(workspace_root=Path.cwd().resolve())

    def set_workspace(self, raw_path: str) -> Path:
        text = (raw_path or "").strip()
        if not text:
            raise ValueError("workspace path is empty")

        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = (self.workspace_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if not candidate.exists():
            raise ValueError(f"workspace does not exist: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"workspace is not a directory: {candidate}")

        self.workspace_root = candidate
        return candidate

    def resolve_path(self, raw_path: str | None = None) -> Path:
        text = (raw_path or ".").strip()
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = (self.workspace_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise ValueError(f"path escapes workspace: {candidate}")

        return candidate

    def support_root(self) -> Path:
        root = (self.workspace_root / ".miniclaw").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def sessions_root(self) -> Path:
        root = (self.support_root() / "sessions").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def temp_root(self) -> Path:
        root = (self.support_root() / "tmp").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def browser_runs_root(self) -> Path:
        root = (self.support_root() / "browser_runs").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def memory_path(self) -> Path:
        return (self.support_root() / "memory.md").resolve()

    def ensure_memory_file(self) -> Path:
        path = self.memory_path()
        if not path.exists():
            path.write_text(DEFAULT_MEMORY_MD, encoding="utf-8")
        return path

    def memory_text(self, *, create: bool = False) -> str:
        path = self.ensure_memory_file() if create else self.memory_path()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def memory_prompt(self, *, max_chars: int = 4000) -> str | None:
        text = self.memory_text(create=False).strip()
        if not text:
            return None

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        suffix = "\n[Memory truncated]" if truncated else ""
        return f"Persistent memory snapshot ({self.memory_path()}):\n{text}{suffix}"

    def append_transcript(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unsupported transcript role: {role}")
        payload = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "role": role,
            "content": content,
        }
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    def prior_transcript_prompt(
        self,
        *,
        max_messages: int = 12,
        max_chars: int = 4000,
    ) -> str | None:
        path = self.resume_transcript_path
        if path is None or not path.exists():
            return None

        entries: list[dict[str, str]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            role = str(parsed.get("role") or "")
            content = str(parsed.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            entries.append({"role": role, "content": content})

        if not entries:
            return None

        excerpt = entries[-max_messages:]
        lines = [
            f"{entry['role'].capitalize()}: {entry['content'].replace(chr(10), ' ')}"
            for entry in excerpt
        ]
        text = "\n".join(lines)
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        suffix = "\n[Transcript truncated]" if truncated else ""
        return f"Recent conversation excerpt from previous session ({path}):\n{text}{suffix}"

    def _latest_session_path(self) -> Path | None:
        paths = sorted(self.sessions_root().glob("*.jsonl"))
        return paths[-1] if paths else None

    def make_temp_path(self, filename: str | None = None, *, suffix: str = ".tmp") -> Path:
        raw = (filename or "").strip()
        if raw:
            base = Path(raw).name.strip()
            if not base:
                raise ValueError("temporary filename is empty")
        else:
            base = f"temp-{uuid.uuid4().hex[:8]}{suffix}"
        path = (self.temp_root() / base).resolve()
        if path != self.temp_root() and self.temp_root() not in path.parents:
            raise ValueError(f"temporary path escapes temp root: {path}")
        return path

    def state_prompt(self) -> str:
        return (
            "Runtime state:\n"
            f"- Current workspace root: {self.workspace_root}\n"
            f"- Temporary work directory: {self.temp_root()}\n"
            f"- Browser artifact root: {self.browser_runs_root()}\n"
            f"- Persistent memory file: {self.memory_path()}\n"
            f"- Current transcript file: {self.transcript_path}\n"
            "- All file paths and commands must stay inside the workspace unless a tool changes it.\n"
            "- For external or current information, prefer web_search and then web_fetch.\n"
            "- For pages that need clicks, typing, waiting, or dynamic DOM state, prefer browser_navigate, browser_snapshot, browser_act, and browser_extract.\n"
            "- If the user explicitly asks to open a site and then search, click, type, or inspect within that site, follow that interaction sequence in the browser instead of jumping straight to a guessed final page.\n"
            "- Once the relevant page is open in the browser, prefer browser_snapshot or browser_extract over generic web tools for the same page.\n"
            "- For Twitter/X account timelines or tweet details, prefer the dedicated twitter_* tools over generic web fetching.\n"
            "- Prefer run_python for quick calculations or validation scripts that do not need to persist.\n"
            "- Prefer write_temp_file for temporary helper scripts; avoid writing scratch files into the workspace root.\n"
            "- Prefer apply_patch for editing existing files; use write_file for new files or full rewrites.\n"
            "- Use the memory tools only for durable preferences, workspace rules, and stable facts.\n"
            "- When the user asks for code changes, inspect files first, then edit, then verify.\n"
        )
