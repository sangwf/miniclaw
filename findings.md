# Findings & Decisions

## Requirements
- Keep the user interaction natural-language first.
- Make workspace selection and use real runtime state, not just conversational memory.
- Let the LLM trigger coding actions automatically through tools.
- Keep execution inside one active workspace.

## Research Findings
- The local environment has `openai` Python SDK `2.21.0`.
- The SDK supports chat completions with tool calls, which fits the current message-history-based design.
- For this version, the default model can stay on the smaller GPT-5.4 tier; runtime improvements still matter more than model changes.
- A separate `SessionState` object is enough to hold the active workspace root without introducing persistence or a complex mode system.
- The first practical tool set is:
  - `set_workspace`
  - `get_workspace`
  - `list_files`
  - `read_file`
  - `search_text`
  - `apply_patch`
  - `write_file`
  - `run_command`
- Returning structured JSON strings from tools makes the model loop easier to reason about than ad hoc plain text.
- Tool visibility works best as agent-level events with CLI-side summarization, rather than printing raw JSON directly from the tool layer.
- Temporary work should not go into the workspace root. A dedicated `.miniclaw/tmp` directory keeps scratch artifacts contained and easy to ignore.
- `run_python` is a better fit than writing one-off scripts for quick calculations and validation, because it executes code directly from stdin without creating files.
- The original tool-budget loop could consume all allowed tool rounds and then terminate before giving the model a final chance to answer. A final no-tool synthesis pass fixes that behavior.
- Existing-file edits need a safer primitive than `write_file`. A structured patch format gives the model an incremental edit path and reduces accidental whole-file clobbering.
- `read_file` currently returns numbered lines for readability. Normalizing those prefixes inside `apply_patch` hunks makes small edits more forgiving when the model copies context from tool output.
- The REPL was still line-oriented, so pasted natural-language prompts with embedded newlines were being split into separate turns.
- A short `select.select(...)` drain window on TTY stdin is enough to coalesce pasted line bursts into one logical message without changing the user-facing command syntax.
- In this desktop terminal setup, `0.08s` was still short enough to split a delayed final pasted line; `0.2s` coalesces that case reliably in pseudo-terminal tests.
- The smallest practical web-research capability is a pair of tools: `web_search` to discover candidate URLs and `web_fetch` to pull readable page text.
- It is possible to implement both tools with the Python standard library; no extra dependency is required for HTTP requests or basic HTML text extraction.
- A useful zero-config fallback is DuckDuckGo's HTML search endpoint. It is less structured than an API, but sufficient for a minimal local agent.
- If `BRAVE_SEARCH_API_KEY` is present, Brave Search can act as the primary provider while DuckDuckGo HTML remains the no-key fallback.
- The user's local shell actually exports `BRAVE_API_KEY`, so the runtime should accept that name as the primary Brave credential and keep `BRAVE_SEARCH_API_KEY` as a compatibility alias.
- `web_fetch` needs to reject binary content and focus on readable `text/*`, `html`, `json`, and similar responses; otherwise the tool will return unusable garbage.
- For `miniclaw`, a Markdown memory snapshot is a better first step than JSONL or vector search. It is readable, easy to hand-edit, and simple to inject into the prompt.
- A small dedicated memory API is still useful even with Markdown storage. `memory_read`, `memory_replace`, and `memory_forget` can keep the file shape stable without forcing the model to hand-author patches for every preference change.
- The memory store can stay as a single `.miniclaw/memory.md` file for now. Daily logs, embeddings, and search indices are unnecessary at this stage.
- Injecting the current `memory.md` snapshot as an extra system message is enough to make the memory influence normal turns while the file stays small.
- `SessionState` should normalize `workspace_root` with `resolve()` so relative paths stay stable even in macOS temporary directories that surface both `/var/...` and `/private/var/...`.
- The user values prior chat history separately from distilled memory. A raw transcript log should therefore be stored independently of `memory.md`.
- A lightweight per-session JSONL file under `.miniclaw/sessions/` is enough to preserve user/assistant turns across restarts.
- Loading only the most recent prior session as a summarized system note is simpler and safer than replaying all historical tool traffic into the live message history.
- Appending only `user` and final `assistant` turns keeps transcript files useful for continuity without bloating them with intermediate tool chatter.
- OpenAI prompt caching keys off the exact prompt prefix, so any frequently changing note placed near the beginning of `messages` reduces cache reuse for later turns. Source: [Prompt Caching Guide](https://platform.openai.com/docs/guides/prompt-caching)
- `miniclaw` currently inserts per-turn notes like tool budget early in the prompt; moving them later should preserve a larger stable prefix without changing the visible interaction model.
- Cached token visibility matters. Without surfacing `cached_tokens`, prompt-cache optimizations are hard to validate interactively.
- Appending the dynamic notes as the final system message preserves a larger stable prefix while keeping the note in-band for the model.
- Exposing `cached_tokens` via an explicit LLM usage event is enough to make cache behavior visible without entangling the model client with terminal formatting.
- `twitter-cli` already provides the three read-only capabilities `miniclaw` needs most here: `whoami`, `user-posts`, and `tweet`.
- Those commands all support `--json`, which makes them much better candidates for dedicated tools than raw `run_command` wrappers.
- `twitter whoami --json` returns a top-level `data.user` object with the authenticated account profile.
- `twitter user-posts <screen_name> --max N --json` returns a top-level `data` list of tweet objects, which is a clean fit for `twitter_user_posts`.
- `twitter tweet <tweet_id> --max N --json` also returns a top-level `data` list, so `twitter_tweet` can reuse the same structured-result pattern.
- For a lightweight local agent, promoting a frequently used external CLI into a dedicated read-only tool reduces tool-selection ambiguity compared with asking the model to synthesize shell commands every time.
- Supporting full tweet URLs in `twitter_tweet` matters because users often paste links, not bare numeric IDs.
- OpenClaw-RL reframes the agent's next-state signal as online training data. User replies, tool outputs, terminal errors, GUI diffs, and test verdicts are all treated as learning signals rather than only as next-turn context. Source: [OpenClaw-RL paper](https://arxiv.org/pdf/2603.10165), [repo README](https://github.com/Gen-Verse/OpenClaw-RL).
- The paper separates next-state feedback into two kinds: evaluative signals (good/bad scalar reward) and directive signals (textual hints about what should have changed). It uses Binary RL for the former and Hindsight-Guided On-Policy Distillation (OPD) for the latter.
- OPD is the paper's most practically interesting idea for a small agent runtime: extract a concise hindsight hint from the next state, append it to the original prompt, and train the model against the hinted version's token distribution instead of relying only on a scalar reward.
- The paper recommends combining broad but coarse Binary RL with sparse but high-resolution OPD. In the personal-agent experiment, the combined method substantially outperformed either method alone after a small number of interactions.
- For general agents, the supported settings are terminal, GUI, SWE, and tool-call environments; the key unifying concept is that each step yields structured next-state feedback such as stdout/stderr, GUI state changes, diffs, or API return values.
- The infrastructure lesson is a four-part async split: policy serving, environment rollout collection, PRM/judge evaluation, and training should run independently so learning never blocks live usage.
- The paper's most directly reusable ideas for `miniclaw` are not the large-scale RL stack itself, but: session-aware interaction logs, explicit distinction between main-line vs side turns, structured process feedback capture, and hindsight hint extraction from tool failures or user corrections.
- For `miniclaw`, harness engineering should mean defining browser goals, constraints, observation schemas, fixture pages, and acceptance tasks before writing browser runtime code.
- Because `miniclaw` already has its own agent loop and tool registry, Playwright is a better likely browser executor than layering in another agent system such as browser-use.
- The first browser acceptance gate should be local and deterministic, based on fixture pages served from the workspace, not public-web behavior.
- Browser implementation should be driven by a small fixed task set and a standard observation contract rather than by exposing raw Playwright capabilities to the model.
- There is no existing docs or fixtures layout for browser work in the repo, so root-level planning documents are the simplest first step.
- The browser harness can be made import-light by lazily importing Playwright only in execution paths that actually need it; this allows `--list-tasks` and `--check-fixtures` to work without browser dependencies installed.
- A standalone fixture server based on `ThreadingHTTPServer` is enough for the first local acceptance loop.
- The first five local fixture pages are sufficient to exercise read, click, type, submit, and wait behaviors.
- A standalone harness runner can already pass all five deterministic acceptance tasks before any `miniclaw` tool integration happens.
- Keeping browser artifacts under `.miniclaw/browser_runs/` fits the current project pattern and stays ignored by `.gitignore`.
- The browser runtime can be factored into a shared module so the standalone harness and the live tool layer use the same execution and observation logic.
- A session-scoped live browser harness keyed by `SessionState.session_id` is sufficient for the first interactive `browser_*` tool integration.
- `browser_navigate`, `browser_snapshot`, `browser_act`, `browser_extract`, and `browser_close` are enough to expose the first browser loop without leaking raw Playwright APIs to the model.
- The browser tool layer can already operate successfully against the local fixture server when run inside a Python environment that has Playwright installed.
- Browser step fidelity needs an extra instruction layer: for explicit requests like “open site, search term, then summarize”, the model otherwise tends to optimize for the final answer and may skip the requested on-page interaction sequence.
- A short per-turn browser-sequence note works better than relying on generic browser preferences alone, because it only activates when the user explicitly asks for ordered UI actions.
- The repo had no remote and no README, but GitHub CLI was already authenticated as `sangwf`, so a minimal public release path was: add README, commit locally, create `sangwf/miniclaw` as a public repo, and push `main`.
- On this machine, the Homebrew-managed `python3` rejects direct global `pip install` under PEP 668, but `python3 -m pip install --user --break-system-packages ...` works and still makes `playwright` importable from the default interpreter.
- The current readability problem is mostly a presentation-layer issue: welcome text, tool traces, usage logs, errors, and final answers all share nearly the same visual weight in the plain-text REPL.
- `rich` is a good fit here because it can improve hierarchy with panels, dim log lines, and styled prompts while keeping a plain-text fallback for environments where it is missing.
- The Chinese backspace artifact is a display-path regression, not a content-path regression: the submitted text is already correct, but `stdin.readline()` on the interactive TTY path is not a good replacement for Python's normal line-editing behavior when IME/CJK input is involved.
- A practical compromise is to use `input()` only for the first interactive line on real `sys.stdin`, then keep the existing select-based drain to coalesce any additional pasted lines that arrive immediately after the first newline.
- For CJK input, it is not enough to switch back to `input()` if the prompt is still rendered separately beforehand. The interactive prompt text itself should also be owned by `input()` so readline/libedit can account for prompt width and cursor movement consistently.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add `session.py` with `SessionState` | Workspace state needs to be explicit and shared across turns |
| Inject runtime state as a dynamic system message before each model call | The model should always see the current workspace without relying on stale text memory |
| Use `shlex.split()` plus blocked-pattern checks in `run_command` | This keeps command execution simple while avoiding shell chaining and obvious destructive commands |
| Add `ToolExecutionEvent` and render compact `[tool]` / `[tool-result]` lines in the REPL | The user wants observability into how the agent is operating |
| Add `SessionState.temp_root()` and `write_temp_file` | Scratch scripts need a dedicated location |
| Add `run_python` and prefer it in the system prompt | Quick computation and validation should not require creating files |
| Improve failed `run_python` / `run_command` summaries to show exit code and stderr | `unknown error` was too opaque during interactive runs |
| Add a restricted `apply_patch` tool with `Begin Patch` / `Update File` / `Add File` / `Delete File` blocks | This gives the agent a safer incremental edit path without requiring a full-blown editor protocol |
| Prefer `apply_patch` for existing files and reserve `write_file` for new files or deliberate rewrites | The smaller the diff, the safer the model's edit loop becomes |
| Replace direct `input()` usage with paste-aware stdin reading | This preserves multi-line pasted prompts as one user turn |
| Add `web_search` and `web_fetch` as a pair instead of search alone | Search without a fetch path leaves the agent unable to inspect result pages |
| Keep web research implementation dependency-free | This preserves the current lightweight installation story for `miniclaw` |
| Represent persistent memory as a current-state Markdown file under `.miniclaw/memory.md` | This keeps the memory legible while still allowing deterministic upserts and deletes |
| Add `memory_read`, `memory_replace`, and `memory_forget` instead of a generic memory event log | The user explicitly wants updates to overwrite current preferences rather than pile up stale entries |
| Inject the memory snapshot directly into the runtime system context | The memory file should influence normal turns without requiring an explicit search step while it remains small |
| Normalize `SessionState.workspace_root` in `__post_init__` | Tool paths and `relative_to(...)` calls should stay consistent across direct construction and workspace changes |
| Persist session transcripts as `.jsonl` files and inject only a recent prior-session excerpt | This preserves conversational continuity without turning the current loop into a heavy state machine |
| Keep transcript persistence separate from the live `self.history` object | Current-turn behavior stays simple while prior-session continuity is still available as a bounded system note |
| For future online learning, treat next-state feedback as its own data product | `miniclaw` should log corrections, errors, and re-queries in a structured way before attempting any RL or fine-tuning |
| Surface `cached_tokens` alongside normal token usage in the REPL | Prompt-cache tuning should be empirically visible instead of guessed |
| Emit a separate LLM usage event from the agent loop | The agent should stay responsible for orchestration while the CLI decides how to render usage |
| Wrap `twitter-cli` behind `twitter_whoami`, `twitter_user_posts`, and `twitter_tweet` | These are high-frequency, high-value read operations with clearer semantics than generic shell execution |
| Keep the first Twitter/X integration read-only | Read operations are immediately useful and avoid the approval/safety complexity of likes, retweets, posts, or deletes |
| Resolve `twitter-cli` from env override, then PATH, then workspace-local virtualenv | This keeps the tools usable whether the CLI is globally installed or only present in `.miniclaw/tmp/venv/bin/twitter` |
| Draft browser support as a harness-first capability instead of an implementation-first feature | The browser project needs a fixed success contract before any runtime code is added |
| Keep the first browser tool surface narrow and observation-rich | A small action vocabulary plus structured observations is easier for the model and easier to evaluate |
| Base Phase-1 browser acceptance on five deterministic local tasks | Stable fixture tasks are a better gate than ad hoc live-web demos |
| Add `requirements-browser.txt` instead of expanding the base `requirements.txt` immediately | Browser automation is optional for now and should not bloat the default install path yet |
| Make the browser harness standalone before wiring it into agent tools | This separates executor validation from agent-loop behavior and makes failures easier to localize |
| Keep the browser runtime lazy-imported and shared | This preserves lightweight non-browser execution while preventing harness/tool drift |
| Key the live browser session off `SessionState.session_id` | One browser session per REPL session is a simple and sufficient first policy |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Existing planning files described the earlier no-tool skeleton | Replaced them with the current LLM-first coding-shell task |
| Numbered `read_file` output could make patch matching brittle | Strip `read_file`-style prefixes from patch hunks before applying them |
| Pasted multi-line prompts were being split into multiple turns | Drain immediately ready TTY stdin lines into one message before dispatching the turn |
| Web search should work even without third-party API keys | Use DuckDuckGo HTML parsing as a fallback behind the optional Brave path |
| The initial Twitter smoke script passed a string into `SessionState(workspace_root=...)` | Fix the test harness to pass `Path('.')`; production code already uses a `Path` |
| The browser feature had no written acceptance boundary yet | Create browser feature, harness, and task documents before implementation starts |
| Tried to install Chromium before the `playwright` package existed in the temp venv | Install `playwright` first, then run `python -m playwright install chromium` |
| Browser tools needed to reuse harness logic without forcing Playwright on non-browser commands | Extract a shared `browser_runtime.py` with lazy imports |
| Homebrew `python3` rejected a direct package install with `externally-managed-environment` | Install Playwright into the user site with `--user --break-system-packages` instead |
| Live browser tools need at least one public-web smoke in addition to local fixtures | Use a simple Wikipedia search flow to validate real navigation, typing, clicking, extraction, and normalized selector errors under the default `python3` environment |

## Resources
- Project root: /Users/sangwf/code/miniclaw
- Session state: /Users/sangwf/code/miniclaw/session.py
- Agent loop: /Users/sangwf/code/miniclaw/agent.py
- Tool registry: /Users/sangwf/code/miniclaw/tools.py
- CLI entrypoint: /Users/sangwf/code/miniclaw/main.py
- Planned memory store: /Users/sangwf/code/miniclaw/.miniclaw/memory.md
- Planned transcript store: /Users/sangwf/code/miniclaw/.miniclaw/sessions/
- Workspace-local twitter-cli: /Users/sangwf/code/miniclaw/.miniclaw/tmp/venv/bin/twitter
- Browser feature spec: /Users/sangwf/code/miniclaw/browser_feature_spec.md
- Browser harness spec: /Users/sangwf/code/miniclaw/browser_acceptance_harness.md
- Browser acceptance tasks: /Users/sangwf/code/miniclaw/browser_acceptance_tasks.md
- Browser fixture pages: /Users/sangwf/code/miniclaw/fixtures/browser
- Browser harness runner: /Users/sangwf/code/miniclaw/scripts/browser_harness.py
- Optional browser dependencies: /Users/sangwf/code/miniclaw/requirements-browser.txt
- Shared browser runtime: /Users/sangwf/code/miniclaw/browser_runtime.py

## Visual/Browser Findings
- Browser work should start from deterministic local fixtures and a standard observation schema instead of public-web smoke tests.
- The current standalone harness passes all five local acceptance tasks in a temporary Playwright environment.
- The live `browser_*` tools can now navigate, snapshot, act, extract, and close against those same fixtures in a Playwright-enabled environment.
- The same live `browser_*` tools also complete a simple public-web flow on Wikipedia under the default `python3` environment; malformed selectors are returned as structured tool errors instead of raw crashes.
- After tightening the prompts, the live agent now follows the public-web Wikipedia flow in order: open `wikipedia.org`, type `Andrej Karpathy`, submit via the page input, and only then summarize the article content without falling back to `web_search`.
- The upgraded REPL now benefits from four visual tiers: a welcome panel, dim operational logs (`tool`/`llm`), a styled `You >` prompt, and a bordered final-answer panel for `Claw`.
- After restoring `input()` on the real TTY path, the REPL keeps the richer visual layer while delegating actual line editing back to the terminal/readline path that handles CJK backspace more reliably.
- The best compromise is asymmetric: keep the rich welcome/log/reply rendering, but let the real interactive prompt itself fall back to a plain `input("You > ")` string on TTY stdin.
