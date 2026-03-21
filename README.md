# miniclaw

`miniclaw` is a minimal LLM-first coding shell built around a simple tool-calling loop.

It focuses on a small but real runtime:

- workspace-aware file inspection and editing
- command execution with bounded safety checks
- lightweight web search and fetch
- a Markdown memory file at `.miniclaw/memory.md`
- persisted chat transcripts under `.miniclaw/sessions/`
- read-only Twitter/X tools powered by `twitter-cli`
- first-class browser tools backed by Playwright

## Requirements

- Python 3.13+
- `OPENAI_API_KEY`

Optional browser support:

- `pip install -r requirements-browser.txt`
- `python -m playwright install chromium`

## Install

```bash
pip install -r requirements.txt
```

For browser tools:

```bash
pip install -r requirements-browser.txt
python -m playwright install chromium
```

## Run

```bash
python3 main.py
```

The agent starts in the current working directory and uses that directory as its active workspace.

## Example Prompts

- `先看看这个项目结构`
- `给 tools.py 加一个新工具，然后跑一下 smoke test`
- `搜索 Andrej Karpathy 最近的 tweets，然后总结观点`
- `打开 wikipedia，搜索 Andrej Karpathy，再总结首页前两段`

## Browser Harness

The browser feature was built with a harness-first workflow.

- feature spec: `browser_feature_spec.md`
- harness contract: `browser_acceptance_harness.md`
- task set: `browser_acceptance_tasks.md`
- standalone runner: `scripts/browser_harness.py`

Run the standalone harness:

```bash
python3 scripts/browser_harness.py --all
```
