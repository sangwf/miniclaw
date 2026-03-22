# Task Plan: Build LLM-First miniclaw Coding Shell

## Goal
Upgrade `miniclaw` from a plain CLI chat loop into an LLM-first coding shell with real session workspace state, visible tool-call traces in the terminal, safer temporary execution primitives, a safer patch-based edit path for existing files, paste-friendly multiline input, basic web research tools, a small persistent Markdown memory, a few high-value read-only Twitter/X tools, and a harness-first browser capability with deterministic fixtures, a standalone runner, and first-class `browser_*` tools.

## Current Phase
Phase 16 complete

## Phases
### Phase 1: Requirements & Discovery
- [x] Confirm the desired interaction model is natural-language driven, not slash-command driven
- [x] Decide to keep workspace as runtime state rather than model-only memory
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Implementation
- [x] Add session state for the active workspace
- [x] Add workspace-aware tools for inspection and execution
- [x] Update the agent prompt and loop to expose runtime state to the model
- [x] Print tool-call activity in the REPL
- [x] Add a temp-work strategy and direct Python execution tool
- **Status:** complete

### Phase 3: Verification & Delivery
- [x] Run static validation
- [x] Smoke test workspace tools directly
- [x] Smoke test a tool-calling agent turn
- **Status:** complete

### Phase 4: Safer Editing Primitive
- [x] Design a minimal structured patch format for workspace edits
- [x] Add an `apply_patch` tool for add/update/delete file operations
- [x] Update prompts and CLI summaries to prefer and explain patch-based edits
- [x] Smoke test direct patch application and agent-driven patch usage
- **Status:** complete

### Phase 5: Multiline Input Handling
- [x] Diagnose why pasted multi-line prompts were being split into separate turns
- [x] Coalesce bursty terminal input into a single user message
- [x] Validate the behavior in a pseudo-terminal smoke test
- **Status:** complete

### Phase 6: Web Research Tools
- [x] Add a minimal `web_search` tool with a no-extra-dependency HTTP path
- [x] Add a `web_fetch` tool so search results can be inspected directly
- [x] Expose the web tools in prompts and CLI summaries
- [x] Run live smoke tests against public websites
- **Status:** complete

### Phase 7: Markdown Memory
- [x] Add a workspace-local `.miniclaw/memory.md` source of truth
- [x] Expose dedicated memory read/update/forget tools for durable notes
- [x] Inject memory into the agent's runtime context on each turn
- [x] Run compile and smoke tests for the new memory workflow
- **Status:** complete

### Phase 8: Transcript Persistence
- [x] Persist user/assistant turns to `.miniclaw/sessions/*.jsonl`
- [x] Load recent prior-session chat context on startup
- [x] Keep the implementation lightweight and compatible with the current REPL loop
- [x] Run compile and smoke tests for transcript persistence
- **Status:** complete

### Phase 9: Prompt Cache Optimization
- [x] Move highly dynamic per-turn notes later in the message list so stable prefixes are more cacheable
- [x] Expose prompt/cache usage details from LLM responses in the REPL
- [x] Verify compile and basic behavior after the message-order change
- **Status:** complete

### Phase 10: Twitter/X Read-Only Tools
- [x] Wrap `twitter-cli` as dedicated read-only tools instead of relying on generic `run_command`
- [x] Add `twitter_whoami`, `twitter_user_posts`, and `twitter_tweet`
- [x] Prefer the dedicated Twitter/X tools in prompts and runtime state
- [x] Add concise REPL summaries for the new tools
- [x] Run compile and live smoke tests against the local authenticated `twitter-cli`
- **Status:** complete

### Phase 11: Browser Harness Planning
- [x] Define a browser feature spec before implementing runtime code
- [x] Define a harness contract with environment, artifacts, and success criteria
- [x] Write the first five deterministic acceptance tasks
- [x] Keep the first browser scope local, deterministic, and Playwright-backed
- **Status:** complete

### Phase 12: Browser Harness Fixtures & Runner
- [x] Create deterministic local fixture pages under `fixtures/browser`
- [x] Add a standalone `scripts/browser_harness.py` runner
- [x] Support task listing and fixture checks without requiring Playwright at import time
- [x] Add optional browser dependency instructions via `requirements-browser.txt`
- [x] Run all five deterministic acceptance tasks successfully in a local Playwright-backed harness
- **Status:** complete

### Phase 13: Browser Runtime & Tools
- [x] Extract reusable browser runtime code into a shared module
- [x] Repoint the standalone harness runner at the shared runtime
- [x] Add `browser_navigate`, `browser_snapshot`, `browser_act`, `browser_extract`, and `browser_close`
- [x] Expose browser guidance in prompts and session runtime state
- [x] Run compile checks plus direct tool smoke tests in a Playwright-enabled environment
- [x] Tighten browser guidance so explicit open/search/click requests are executed in order instead of shortcutting to a guessed destination page
- **Status:** complete

### Phase 14: Public GitHub Release
- [x] Check git state, remote configuration, and GitHub authentication
- [x] Run a minimal repository hygiene pass before publishing
- [x] Add a minimal public-facing README
- [x] Commit the current project state
- [x] Create the public GitHub repository and push `main`
- **Status:** complete

### Phase 15: CJK Input Validation
- [x] Revert the bad public GitHub commit instead of rewriting public history
- [x] Run controlled PTY experiments for Chinese input plus backspace
- [x] Compare built-in TTY readers with a `prompt_toolkit` path
- [x] Validate multiline bracketed paste on the candidate path
- [x] Integrate the candidate path locally without pushing it yet
- **Status:** complete

### Phase 16: Restore Terminal UI After Revert
- [x] Separate the Rich UI layer from the reverted input-path commit
- [x] Reapply the colored welcome, tool, usage, and reply rendering on top of the `prompt_toolkit` reader
- [x] Verify that Rich UI output does not regress CJK backspace or multiline paste behavior
- **Status:** complete

## Key Questions
1. How can workspace state be real and mutable without requiring explicit slash commands?
2. Which tools are enough to start coding inside a workspace?
3. How do we keep the LLM flexible while still enforcing workspace boundaries?
4. How can the CLI show tool activity without dumping full raw JSON for every step?
5. How do we stop temporary validation scripts from polluting the workspace root?
6. How do we make existing-file edits safer than whole-file rewrites?
7. How do we keep natural-language multi-line prompts from being split into multiple turns in the terminal?
8. How do we let the agent access external information without adding a heavy browser stack or extra dependencies?
9. What is the smallest persistent memory design that stays readable, editable, and useful?
10. What is the smallest transcript persistence mechanism that helps the agent remember prior chat sessions?
11. How can prompt construction preserve more stable prefixes for API-side prompt caching?
12. How can we expose direct Twitter/X lookups without forcing the model to shell out through `run_command`?
13. How do we add browser capability without drifting into ad hoc demos or an oversized tool surface?
14. How do we bridge the standalone browser harness into `miniclaw` tool calls without losing the harness contract?
15. How should the browser runtime be represented in long-running session state once browser usage becomes common?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Default the workspace to the current process directory | This makes “work in the current project” work immediately |
| Let the LLM control workspace changes through tools | It preserves natural-language interaction while keeping runtime state authoritative |
| Add `set_workspace`, `get_workspace`, `list_files`, `read_file`, `search_text`, `write_file`, and `run_command` first | This is the smallest set that enables real repository work |
| Emit concise tool start/finish events from the agent and render them in `main.py` | This keeps runtime visibility without coupling the agent loop to terminal formatting |
| Add `.miniclaw/tmp` plus `write_temp_file` and `run_python` | The agent needs a clean place for scratch work and an easy non-persistent execution path |
| Force one final no-tool synthesis pass after the tool budget is spent | This avoids ending a solved task with `Tool loop limit reached.` |
| Add a structured `apply_patch` tool and prefer it for existing files | Incremental patches are safer and easier to verify than whole-file rewrites |
| Coalesce quick successive terminal lines into one message | This preserves pasted multi-line prompts without forcing a new command syntax |
| Add `web_search` plus `web_fetch` using the standard library | This gives the agent a minimal external-information path without bringing in browser automation yet |
| Prefer Brave Search when `BRAVE_SEARCH_API_KEY` is set, otherwise fall back to DuckDuckGo HTML search | This keeps the feature usable out of the box while still supporting a cleaner paid API path |
| Store durable memory in `.miniclaw/memory.md` and treat it as a current-state snapshot | Markdown is easy for both the user and the agent to read and edit without introducing vector stores or append-only cleanup logic |
| Persist chat transcripts separately from `memory.md` | Durable memory and raw session history solve different problems and should not be conflated |
| Put highly dynamic turn notes as late as possible in the prompt | Prompt caching depends on the exact prefix, so early-changing notes waste cacheable context |
| Promote `twitter-cli` into three dedicated read-only tools | Recent-tweet lookups are common enough to justify clearer schemas and safer usage than `run_command` |
| Plan browser support with a harness-first workflow before implementation | The hardest part is defining success, constraints, and observations, not calling Playwright APIs |
| Keep the first browser harness executable outside the main agent loop | A standalone runner makes executor debugging and acceptance testing simpler before tool integration |
| Share browser execution code between the standalone harness and the tool layer | Separate browser implementations would drift and invalidate the harness-first design |
| Treat explicit browser interaction requests as ordered UI steps | Users may care about the actual path through the page, not just the final answer, and honoring that path reduces unnecessary fallbacks to generic web tools |
| Add a minimal README before publishing the repository | A public repo should at least explain what the project is, how to run it, and what the browser harness files are for |
| Prefer `prompt_toolkit` on the real interactive TTY path | Controlled PTY experiments show better character-level handling for Chinese backspace while still preserving multiline bracketed paste |
| Restore the Rich terminal UI independently of the input backend | Terminal styling and input correctness should be validated separately so a bad input fix does not force a full UX rollback |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `memory_read` smoke test failed in a temporary workspace because `workspace_root` and resolved child paths used different absolute prefixes (`/var/...` vs `/private/var/...`) | 1 | Normalize `SessionState.workspace_root` with `resolve()` in `__post_init__` |
| None during transcript persistence | 1 | N/A |
| None during prompt-cache optimization | 1 | N/A |
| Initial Twitter tool smoke script passed `workspace_root='.'` as a string to `SessionState` | 1 | Fix the test harness to pass `Path('.')`; the runtime itself already constructs `SessionState` with `Path` objects |
| No existing browser docs or fixture layout existed in the repo | 1 | Draft new root-level browser planning documents first, then let implementation follow those contracts |
| Attempted to install Chromium before `playwright` had been installed into the temp venv | 1 | Wait for `pip install -r requirements-browser.txt` to finish, then run `python -m playwright install chromium` |
| `browser_snapshot` and other interactive tools need Playwright in the active Python environment, while `--list-tasks` should not | 1 | Keep Playwright imports lazy in `browser_runtime.py` so non-browser modes stay lightweight |

## Notes
- `run_command` intentionally blocks shell operators and a small set of dangerous patterns.
- File access is restricted to the active workspace via `SessionState.resolve_path(...)`.
- `apply_patch` currently supports `*** Add File`, `*** Update File`, and `*** Delete File` blocks plus `@@` hunks for updates.
- Update hunks tolerate `read_file`-style line-number prefixes, so the model does not need perfect raw-line reconstruction to make a small edit.
- Multiline coalescing uses a short readiness window on TTY stdin, so pasted bursts are merged while normal single-line interaction still feels immediate.
- The initial 80 ms linger was too short for some desktop paste timings; 200 ms handles delayed final lines more reliably.
- `web_search` does not require extra Python packages. It uses Brave Search if `BRAVE_SEARCH_API_KEY` exists, then falls back to DuckDuckGo HTML parsing.
- `web_search` now accepts either `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`, preferring `BRAVE_API_KEY` to match the user's existing shell config.
- `web_fetch` is intentionally text-oriented: it accepts public `http`/`https` URLs and extracts readable content from HTML or other textual responses.
- The memory mechanism should optimize for clarity over retrieval sophistication: a single Markdown snapshot plus a few narrow tools is enough for the current `miniclaw` scope.
- Chat transcripts should survive process exit, but they do not need full database machinery yet; a per-session JSONL log plus recent-session replay is enough for now.
- Prompt-cache effectiveness depends on keeping the earliest messages stable. Notes like `tool_budget_remaining` should not sit near the front of the prompt.
- `twitter-cli` discovery now checks `MINICLAW_TWITTER_CLI_BIN`, then `PATH`, then `.miniclaw/tmp/venv/bin/twitter` in the active workspace.
- The Twitter/X tools are intentionally read-only: `twitter_whoami`, `twitter_user_posts`, and `twitter_tweet`.
- `twitter_tweet` now accepts either a numeric tweet ID or a full `x.com` / `twitter.com` status URL and normalizes it before calling `twitter-cli`.
- Browser capability should start from deterministic local fixture pages, not public websites, so acceptance remains stable.
- The first browser planning artifacts live in the project root: `browser_feature_spec.md`, `browser_acceptance_harness.md`, and `browser_acceptance_tasks.md`.
- The first browser implementation artifacts now live under `fixtures/browser/` and `scripts/browser_harness.py`.
- `requirements-browser.txt` keeps Playwright optional instead of forcing the dependency into the base CLI install path.
- Browser runtime logic now lives in `browser_runtime.py` and is shared by both the standalone harness runner and the `browser_*` tools.
- When the user explicitly says to open a site and then search, click, or type inside it, the agent should stay on the browser path and execute those steps in order before summarizing.
- The public remote for this project is `https://github.com/sangwf/miniclaw`.
- A `prompt_toolkit`-based first-line reader currently looks like the strongest local fix for CJK deletion artifacts: in the PTY experiment it returned the expected `你好` after two backspaces, and it preserved `alpha\\nbeta\\ngamma` when fed as bracketed paste.
- The Rich terminal UI should remain a separate layer over the current input path: welcome panel, colored tool/LLM lines, and boxed Markdown replies can be reintroduced without changing how the first line is read.
