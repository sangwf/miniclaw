# Progress Log

## Session: 2026-03-08

### Phase 1: Requirements & Discovery
- **Status:** complete
- **Started:** 2026-03-08 20:xx Asia/Shanghai
- Actions taken:
  - Confirmed the target interaction style is natural-language driven.
  - Chose an LLM-first design where the model changes workspace through tools instead of slash commands.
  - Reframed the previous “minimal CLI” skeleton into a coding-shell runtime.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 2: Implementation
- **Status:** complete
- Actions taken:
  - Added `session.py` with `SessionState`.
  - Updated `tools.py` to include workspace-aware inspection, write, and command tools.
  - Updated `agent.py` to accept session state and inject runtime state before each model call.
  - Updated `main.py` to initialize the session from the current working directory.
  - Added agent tool-execution events and concise REPL logging for tool start/finish.
  - Added `.miniclaw/tmp`, `write_temp_file`, and `run_python`.
  - Updated the agent prompt to prefer temporary or non-persistent execution paths for scratch work.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/session.py` (created)
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 3: Verification & Delivery
- **Status:** complete
- Actions taken:
  - Ran `python3 -m py_compile` across all modules.
  - Exercised `get_workspace`, `list_files`, `read_file`, and `run_command` directly.
  - Ran a fake-LLM smoke test where the agent made a tool call and completed the turn.
  - Verified the terminal formatting for tool start/result summaries.
  - Verified `write_temp_file` writes under `.miniclaw/tmp`.
  - Verified `run_python` executes code directly and returns structured output.
  - Fixed the tool-loop termination behavior so the model still gets a final synthesis pass after max tool usage.
  - Improved failed `run_python` and `run_command` summaries to show exit code and stderr.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/.gitignore` (updated)

### Phase 4: Safer Editing Primitive
- **Status:** complete
- Actions taken:
  - Added a restricted `apply_patch` tool that supports `*** Add File`, `*** Update File`, and `*** Delete File` blocks.
  - Implemented hunk application for `@@` update blocks using exact context matching inside the active workspace.
  - Normalized `read_file`-style line-number prefixes inside patch hunks to make small edits more forgiving.
  - Updated the system prompt and runtime-state prompt to prefer `apply_patch` for existing-file edits.
  - Updated CLI tool summaries so `apply_patch` shows concise operation and path previews.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 5: Multiline Input Handling
- **Status:** complete
- Actions taken:
  - Replaced the direct `input()` loop with a paste-aware `_read_user_text(...)` helper in `main.py`.
  - Added a short TTY readiness window so quick successive pasted lines are merged into one logical user message.
  - Kept non-TTY behavior simple so piped input does not unexpectedly drain the whole stream into one turn.
  - Increased the paste linger from `0.08s` to `0.2s` after a real split-turn report from the desktop terminal.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 6: Web Research Tools
- **Status:** complete
- Actions taken:
  - Added a dependency-free `web_search` tool with Brave Search as the optional primary provider and DuckDuckGo HTML parsing as the fallback.
  - Added a `web_fetch` tool that extracts readable text from public URLs and rejects non-textual content types.
  - Updated prompts so the agent uses `web_search` and `web_fetch` for external or current information.
  - Updated CLI tool summaries to show concise search and fetch activity.
  - Adjusted Brave credential lookup to accept the user's existing `BRAVE_API_KEY` env var and keep `BRAVE_SEARCH_API_KEY` as a fallback alias.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 7: Markdown Memory
- **Status:** complete
- Actions taken:
  - Added `.miniclaw/memory.md` as the persistent Markdown memory file for the active workspace.
  - Added `memory_read`, `memory_replace`, and `memory_forget` tools to manage durable preferences, workspace rules, and stable facts.
  - Updated `SessionState` with memory helpers and automatic memory snapshot injection into each model turn.
  - Updated prompts so the model treats memory as a durable current-state store instead of a scratch log.
  - Updated REPL tool summaries so memory operations are visible during interactive use.
  - Normalized `SessionState.workspace_root` in `__post_init__` after a temporary-directory path mismatch surfaced during smoke testing.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/.miniclaw/memory.md` (created)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 8: Transcript Persistence
- **Status:** complete
- Actions taken:
  - Added per-session transcript files under `.miniclaw/sessions/`.
  - Logged `user` and final `assistant` turns to the active session transcript.
  - Loaded the most recent previous session as a bounded system note so fresh restarts still remember recent chat context.
  - Printed the resumed transcript path at startup when prior chat history exists.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

### Phase 9: Prompt Cache Optimization
- **Status:** complete
- Actions taken:
  - Moved per-turn dynamic notes to the end of the constructed message list to preserve a larger stable prompt prefix.
  - Parsed token usage and cached token counts from OpenAI responses.
  - Added an agent-level LLM usage event and rendered concise `[llm]` lines in the REPL.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/llm.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

## Session: 2026-03-13

### Phase 10: Twitter/X Read-Only Tools
- **Status:** complete
- Actions taken:
  - Added dedicated read-only `twitter_whoami`, `twitter_user_posts`, and `twitter_tweet` tools backed by `twitter-cli --json`.
  - Added `twitter-cli` resolution logic that checks `MINICLAW_TWITTER_CLI_BIN`, then `PATH`, then `.miniclaw/tmp/venv/bin/twitter`.
  - Updated prompts and runtime-state guidance so the agent prefers the new Twitter/X tools over generic web tools for direct timeline or tweet lookups.
  - Added concise REPL summaries for Twitter tool arguments and results.
  - Normalized tweet URLs to numeric IDs before invoking `twitter-cli` so pasted `x.com/.../status/...` links work directly.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)

## Session: 2026-03-21

### Phase 11: Browser Harness Planning
- **Status:** complete
- Actions taken:
  - Chose a harness-first development approach for browser capability instead of implementation-first Playwright work.
  - Drafted a browser feature spec covering scope, non-goals, constraints, observation contract, and target runtime shape.
  - Drafted an acceptance harness spec covering fixtures, local test server, runner, artifacts, verifier, and rollout gates.
  - Drafted the first five deterministic browser acceptance tasks for local fixture pages.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/browser_feature_spec.md` (created)
  - `/Users/sangwf/code/miniclaw/browser_acceptance_harness.md` (created)
  - `/Users/sangwf/code/miniclaw/browser_acceptance_tasks.md` (created)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 12: Browser Harness Fixtures & Runner
- **Status:** complete
- Actions taken:
  - Created five deterministic local fixture pages under `fixtures/browser`.
  - Added `scripts/browser_harness.py` as a standalone Playwright-backed acceptance runner.
  - Kept the script import-light so `--list-tasks` and `--check-fixtures` work without Playwright installed.
  - Added `requirements-browser.txt` for optional browser dependencies.
  - Created a temporary venv under `.miniclaw/tmp/browser-harness-venv`, installed Playwright, installed Chromium, and ran the harness.
  - Verified the full `--all` batch passes all five deterministic tasks.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/fixtures/browser/simple_page.html` (created)
  - `/Users/sangwf/code/miniclaw/fixtures/browser/click_page.html` (created)
  - `/Users/sangwf/code/miniclaw/fixtures/browser/search_page.html` (created)
  - `/Users/sangwf/code/miniclaw/fixtures/browser/form_page.html` (created)
  - `/Users/sangwf/code/miniclaw/fixtures/browser/dynamic_page.html` (created)
  - `/Users/sangwf/code/miniclaw/scripts/browser_harness.py` (created)
  - `/Users/sangwf/code/miniclaw/requirements-browser.txt` (created)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 13: Browser Runtime & Tools
- **Status:** complete
- Actions taken:
  - Extracted shared browser execution logic into `browser_runtime.py`.
  - Updated `scripts/browser_harness.py` to use the shared runtime instead of its own private browser implementation.
  - Added session-scoped live browser handling and first-class `browser_navigate`, `browser_snapshot`, `browser_act`, `browser_extract`, and `browser_close` tools.
  - Updated prompts, runtime-state guidance, and CLI tool summaries for browser usage.
  - Ran compile checks, standalone harness regression checks, and direct tool smoke tests using a Playwright-enabled temp venv.
  - Installed Playwright and Chromium into the default Homebrew `python3` user site so `python3 main.py` can use the new browser tools directly.
  - Tightened browser prompting so explicit open/search/click user requests are executed in order instead of shortcutting to a guessed destination page or generic web tools.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/browser_runtime.py` (created)
  - `/Users/sangwf/code/miniclaw/scripts/browser_harness.py` (updated)
  - `/Users/sangwf/code/miniclaw/tools.py` (updated)
  - `/Users/sangwf/code/miniclaw/session.py` (updated)
  - `/Users/sangwf/code/miniclaw/agent.py` (updated)
  - `/Users/sangwf/code/miniclaw/main.py` (updated)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 14: Public GitHub Release
- **Status:** complete
- Actions taken:
  - Checked the local git state, confirmed there was no remote, and verified `gh` authentication for account `sangwf`.
  - Ran a minimal public-release hygiene pass: validated `.gitignore`, checked for obvious secrets, and added a short `README.md`.
  - Committed the current project state as `Build miniclaw coding shell`.
  - Created the public GitHub repository `sangwf/miniclaw` and pushed `main`.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/README.md` (created)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 15: Terminal UI Readability
- **Status:** complete
- Actions taken:
  - Reviewed the existing plain-text REPL output and kept the agent/runtime logic unchanged.
  - Added `rich`-backed rendering for the welcome area, prompt, tool logs, usage logs, errors, and final replies.
  - Rendered final assistant replies inside a bordered Markdown panel titled `Claw`.
  - Rendered the startup state inside a compact welcome panel and changed the prompt to `You >`.
  - Kept the old plain-text behavior as a fallback when `rich` is unavailable.
  - Added `rich` to `requirements.txt`.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/main.py` (updated)
  - `/Users/sangwf/code/miniclaw/requirements.txt` (updated)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 16: CJK Input Editing Fix
- **Status:** complete
- Actions taken:
  - Diagnosed the Chinese backspace artifact as an input-path regression introduced when the REPL switched from `input()` to raw `stdin.readline()` for the first interactive line.
  - Changed `_read_user_text(...)` so real `sys.stdin` TTY sessions use `input()` for the first line and then keep the existing select-based drain for any immediately pasted follow-up lines.
  - Kept the non-interactive and custom-stream code paths on the simpler `stream.readline()` behavior.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/main.py` (updated)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

### Phase 17: Prompt Ownership Fix
- **Status:** complete
- Actions taken:
  - Refined the CJK deletion root cause: even after restoring `input()`, separately rendering a styled prompt before calling `input()` can still desynchronize prompt width accounting from readline/libedit's editing model.
  - Changed the real interactive TTY path to call `input("You > ")` directly.
  - Kept the styled `_print_prompt()` path only for non-interactive or custom-stream scenarios.
- Files created/modified:
  - `/Users/sangwf/code/miniclaw/main.py` (updated)
  - `/Users/sangwf/code/miniclaw/task_plan.md` (updated)
  - `/Users/sangwf/code/miniclaw/findings.md` (updated)
  - `/Users/sangwf/code/miniclaw/progress.md` (updated)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Static compile | `python3 -m py_compile ...` | All modules compile | Passed | ✓ |
| Workspace tool smoke | Direct calls into `ToolRegistry.run(...)` | Tools return structured results inside workspace | Passed for `get_workspace`, `list_files`, `read_file`, `run_command` | ✓ |
| Tool-calling agent smoke | Fake LLM emits `get_workspace` tool call | Agent executes tool and returns final reply | Passed | ✓ |
| Tool trace formatting | Manual `_print_tool_event(...)` calls | REPL shows readable tool activity | Printed concise `[tool]` and `[tool-result]` lines | ✓ |
| Temp file tool smoke | `write_temp_file` direct call | Writes into `.miniclaw/tmp` | Passed (`.miniclaw/tmp/scratch.py`) | ✓ |
| Direct Python execution | `run_python` direct call | Executes without creating a file | Passed (`stdout` returned `30`) | ✓ |
| Final synthesis after tool budget | Fake LLM using all tool rounds | Agent still returns a final answer | Passed (`final synthesis`) | ✓ |
| Failed Python summary | Manual `_print_tool_event(...)` with `ok=false` result | Show exit code and stderr | Passed (`exit=1 ... stderr='Traceback...'`) | ✓ |
| apply_patch smoke | Direct `ToolRegistry.run('apply_patch', ...)` | Add, update, and delete a temp file | Passed for add/update/delete | ✓ |
| Numbered patch tolerance | Update temp file using `read_file`-style `N:` prefixes | Patch still applies cleanly | Passed (`gamma -> delta`) | ✓ |
| Agent patch turn | Fake LLM emits `apply_patch` tool call | Agent applies patch and returns final reply | Passed (`agent-patch.txt` created, then cleaned up) | ✓ |
| apply_patch CLI summary | `_summarize_tool_arguments/result` for `apply_patch` | Show concise operation preview | Passed (`ops=1 update:agent.py`) | ✓ |
| Static compile after input change | `python3 -m py_compile main.py` | Updated REPL still compiles | Passed | ✓ |
| Multiline paste coalescing | Pseudo-terminal writes `alpha\\nbeta\\ngamma\\n` quickly | REPL input layer returns one message with embedded newlines | Passed (`'alpha\\nbeta\\ngamma'`) | ✓ |
| Delayed final pasted line | Pseudo-terminal writes the last line after `120ms` | REPL still returns one merged message | Passed | ✓ |
| Static compile after web tools | `python3 -m py_compile main.py agent.py llm.py session.py tools.py` | Updated tool layer still compiles | Passed | ✓ |
| web_search live smoke | Direct `ToolRegistry.run('web_search', ...)` with `OpenAI official site` | Return a small list of public search results | Passed via DuckDuckGo HTML fallback | ✓ |
| web_fetch live smoke | Direct `ToolRegistry.run('web_fetch', ...)` with `https://example.com` | Return title and readable text | Passed (`Example Domain`) | ✓ |
| Brave env alias compile check | `python3 -m py_compile tools.py` | Alias change keeps tool layer valid | Passed | ✓ |
| Static compile after memory tools | `python3 -m py_compile main.py agent.py llm.py session.py tools.py` | Memory changes compile cleanly | Passed | ✓ |
| Memory tool smoke | Direct `memory_read`, `memory_replace`, `memory_forget` calls in a temporary workspace | Template creation, overwrite-style update, and forget all work | Passed | ✓ |
| Memory prompt injection | Create temp `memory.md` then inspect `Agent._messages_with_runtime_state(...)` | Memory snapshot appears as a system message | Passed | ✓ |
| Static compile after transcript persistence | `python3 -m py_compile main.py agent.py llm.py session.py tools.py` | Transcript changes compile cleanly | Passed | ✓ |
| Transcript persistence smoke | Create one session, append user/assistant turns, then open a new session in the same workspace | Previous transcript is found and summarized into the next session context | Passed | ✓ |
| Static compile after prompt-cache optimization | `python3 -m py_compile main.py agent.py llm.py session.py tools.py` | Cache-related changes compile cleanly | Passed | ✓ |
| Prompt cache smoke | Fake LLM run with memory + prior transcript context | Dynamic notes appear as the final message and cached token usage events are emitted | Passed | ✓ |
| Static compile after Twitter tools | `python3 -m py_compile main.py agent.py llm.py session.py tools.py` | Twitter tool integration compiles cleanly | Passed | ✓ |
| twitter_whoami smoke | Direct `ToolRegistry.run('twitter_whoami', '{}')` | Return authenticated account profile from `twitter-cli` | Passed (`authenticated=true`, user `sangwf2001`) | ✓ |
| twitter_user_posts smoke | Direct `ToolRegistry.run('twitter_user_posts', {'screen_name':'karpathy','max_items':1})` | Return a structured recent-post list | Passed (`count=1`, latest Karpathy tweet fetched) | ✓ |
| twitter_tweet URL smoke | Direct `ToolRegistry.run('twitter_tweet', {'tweet_id':'https://x.com/karpathy/status/2031792523187040643','max_replies':1})` | Accept a full tweet URL and return tweet details | Passed (`tweet_id` normalized to `2031792523187040643`) | ✓ |
| Browser harness document draft | Create browser planning artifacts in project root | Specs clearly define feature scope, harness contract, and first 5 tasks | Passed | ✓ |
| Browser harness compile | `python3 -m py_compile scripts/browser_harness.py` | Harness runner compiles | Passed | ✓ |
| Browser harness list mode | `python3 scripts/browser_harness.py --list-tasks` | Print the 5 task specs without Playwright | Passed | ✓ |
| Browser harness fixture check | `python3 scripts/browser_harness.py --check-fixtures` | Serve local fixtures and fetch all 5 pages successfully | Passed | ✓ |
| Browser harness single-task smoke | `python scripts/browser_harness.py --task browser_task_001_read_simple_page` in temp Playwright venv | First task passes end-to-end in real browser | Passed | ✓ |
| Browser harness full batch | `python scripts/browser_harness.py --all` in temp Playwright venv | All 5 deterministic browser tasks pass | Passed (`5/5`) | ✓ |
| Browser runtime compile | `python3 -m py_compile browser_runtime.py scripts/browser_harness.py tools.py session.py agent.py main.py` | Shared runtime and browser tool integration compile cleanly | Passed | ✓ |
| Browser harness regression after refactor | `python scripts/browser_harness.py --all` in temp Playwright venv | Shared runtime refactor does not break the standalone harness | Passed (`5/5`) | ✓ |
| browser_* tool smoke | Direct `ToolRegistry.run(...)` calls for `browser_navigate`, `browser_snapshot`, `browser_act`, `browser_extract`, and `browser_close` in temp Playwright venv | The live tool layer works end-to-end against local fixtures | Passed | ✓ |
| Default python3 browser smoke | Direct `ToolRegistry.run(...)` calls for `browser_navigate`, `browser_act`, `browser_extract`, and `browser_close` using `/opt/homebrew/bin/python3` | The default interpreter can use browser tools after user-site Playwright install | Passed | ✓ |
| Public-web browser smoke | Direct `ToolRegistry.run(...)` calls against `https://www.wikipedia.org/` to search for `Andrej Karpathy` and extract the destination page text using default `python3` | Real public-site navigation, typing, clicking, extraction, and close all work in the default interpreter | Passed (`current_url=https://en.wikipedia.org/wiki/Andrej_Karpathy`) | ✓ |
| Live ordered-browser agent smoke | Real `Agent.run_turn(...)` with `gpt-5.4-mini`: `打开 wikipedia，搜索 Andrej Karpathy，再总结首页前两段` | The agent should open Wikipedia first, then type/search on-page, and summarize from the browser session without falling back to generic web tools | Passed (`browser_navigate -> browser_act(type) -> browser_act(press)` then final reply) | ✓ |
| Public GitHub release | `gh repo create sangwf/miniclaw --public --source=... --remote=origin --push` | Create a public repository and push the current `main` branch | Passed (`https://github.com/sangwf/miniclaw`) | ✓ |
| Rich UI compile | `python3 -m py_compile main.py` | The new presentation layer compiles cleanly | Passed | ✓ |
| Rich UI startup smoke | Launch `python3 main.py` in a TTY and immediately exit | Welcome panel, styled prompt, and clean exit all render correctly | Passed | ✓ |
| CJK input-path compile | `python3 -m py_compile main.py` | The new first-line input path compiles cleanly | Passed | ✓ |
| CJK input-path startup smoke | Launch `python3 main.py` in a TTY and immediately exit after the `input()`-based prompt path is active | Startup panel, prompt, and exit still behave normally after restoring `input()` on real TTY stdin | Passed | ✓ |
| Prompt-ownership compile | `python3 -m py_compile main.py` | The prompt ownership change compiles cleanly | Passed | ✓ |
| Prompt-ownership startup smoke | Launch `python3 main.py` in a TTY and immediately exit after switching to `input(\"You > \")` on the interactive path | Welcome panel, prompt, and exit still behave normally with prompt ownership moved into `input()` | Passed | ✓ |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
|           |       | 1       |            |
| 2026-03-13 | Twitter smoke script raised `AttributeError: 'str' object has no attribute 'resolve'` | 1 | Updated the test harness to use `SessionState(workspace_root=Path('.'))` |
| 2026-03-21 | No existing browser doc/fixture layout was present in the repo | 1 | Started with root-level design artifacts instead of forcing an arbitrary docs tree up front |
| 2026-03-21 | `python -m playwright install chromium` failed because `playwright` was not yet installed in the temp venv | 1 | Finished `pip install -r requirements-browser.txt`, then reran the browser install successfully |
| 2026-03-21 | Browser support needed to stay lightweight when Playwright is absent | 1 | Moved browser imports behind `load_playwright()` so non-browser commands and document modes still run without the dependency |
| 2026-03-21 | Homebrew `python3` blocked a direct `pip install` with `externally-managed-environment` | 1 | Installed Playwright with `python3 -m pip install --user --break-system-packages -r requirements-browser.txt` and then ran `python3 -m playwright install chromium` |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 17 complete |
| Where am I going? | The next phase is turning the current browser tools into a more agent-friendly experience with stronger element targeting and richer browser state management |
| What's the goal? | Build an LLM-first coding shell with real workspace state, safe editing primitives, usable terminal interaction, basic external research, lightweight persistent memory, persisted chat transcripts, cache-friendly prompts, direct Twitter/X read tools, and a harness-first browser capability |
| What have I learned? | Natural-language interaction can stay flexible if workspace state and tool boundaries are enforced in runtime |
| What have I done? | Implemented session state, workspace-aware tools, visible tool traces, a structured patch tool, paste-friendly multiline input, basic web research tools, a small persistent Markdown memory, per-session chat transcripts, prompt-cache-aware usage reporting, direct read-only Twitter/X tools, a harness-first browser design package, a passing standalone browser acceptance runner, first-class `browser_*` tools backed by the shared browser runtime, published the project as a public GitHub repository, upgraded the terminal UI with a richer visual hierarchy, and fixed the interactive CJK backspace display regression by restoring `input()` and prompt ownership on the real TTY path |

## Research Notes
- Reviewed the OpenClaw-RL paper ([arXiv:2603.10165](https://arxiv.org/pdf/2603.10165)) and project repository ([Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)).
- Key takeaway: the most reusable idea for `miniclaw` is to log and reuse next-state feedback structurally, especially user corrections and tool-failure traces, before trying to copy the paper's full asynchronous RL stack.
- Probed the locally installed `twitter-cli` and confirmed that `whoami`, `user-posts`, and `tweet` all emit stable top-level JSON with `--json`, which made them good candidates for dedicated tools.
- Chose a harness-first browser planning flow: define feature scope, harness contract, and deterministic task set before adding any Playwright runtime code.
- Implemented the first standalone browser harness runner and confirmed that the initial five acceptance tasks pass end-to-end in a temporary Playwright environment.
- Refactored the browser execution layer into a shared runtime module and confirmed that both the standalone harness and the live `browser_*` tools work against the same fixture pages.
- Confirmed the same live browser tools also work against a real public site by navigating Wikipedia, typing a search, clicking submit, extracting page text, and closing the session under the default `python3` environment.
