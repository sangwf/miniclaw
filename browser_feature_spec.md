# Browser Feature Spec for miniclaw

## Purpose
Define the first browser-interaction capability for `miniclaw` using a harness-first approach. This document describes the target behavior, constraints, observation contract, and acceptance boundaries before any browser runtime is implemented.

## Product Goal
Enable `miniclaw` to complete a small set of deterministic browser tasks inside a real browser session, with structured observations and bounded actions, while preserving the current LLM-first tool loop and runtime safety model.

## Scope

### In Scope for Phase 1
- Open a page in a real browser.
- Read page state in a structured way.
- Click a visible interactive element.
- Type into a visible input and submit.
- Extract user-visible text and simple structured result lists.
- Save screenshots and step traces for debugging and evaluation.
- Run against deterministic local fixture pages first.

### Out of Scope for Phase 1
- Login flows.
- File uploads and downloads.
- Multi-tab workflows.
- Arbitrary JavaScript execution from the model.
- Browser extensions.
- Cross-session browser persistence.
- Complex anti-bot or captcha handling.
- Public-web acceptance as the primary test gate.

## User-Facing Goal
The user should be able to ask for simple webpage interactions in natural language, and `miniclaw` should complete them through bounded browser tools without needing raw Playwright code or shell commands.

## Target Tasks
Phase 1 browser support should reliably handle these task shapes:
- Open a page and report its title and visible content.
- Click a button or link and observe the updated page.
- Fill a search or form field and submit it.
- Extract the top N visible items from a result list.
- Wait for a deterministic dynamic update and then continue.

## Non-Goals
- Replacing `web_search` and `web_fetch` for simple static public pages.
- Full browser automation parity with OpenClaw or browser-use.
- Free-form browser scripting by the model.
- Benchmark-grade web capability on day one.

## Design Principles
- Harness first: the implementation must satisfy a fixed task and observation contract.
- Deterministic first: acceptance should start from controlled local fixtures.
- Few tools, rich observations: keep the tool surface small and let the harness return structured state.
- No raw Playwright exposure: the model should not receive unrestricted browser code execution.
- Replayable traces: every run should produce enough artifacts to debug failures.

## Proposed Runtime Shape

### Browser Backend
- Use Playwright as the browser executor.
- Keep Playwright behind a local browser harness layer.

### Harness Layer
The harness owns:
- Browser lifecycle.
- Page state capture.
- Action execution.
- Timeout and error normalization.
- Artifact capture.
- Structured observations.

### Tool Surface
Phase 1 should expose a small browser tool set:
- `browser_navigate(url)`
- `browser_snapshot()`
- `browser_act(action, target, value=None)`
- `browser_extract(kind="text" | "list")`
- `browser_close()`

These tool names are provisional. The important constraint is that the model sees a narrow action vocabulary and a stable observation format.

## Constraints

### Interaction Constraints
- Single browser session.
- Single tab.
- Single active page.
- One action per tool call.
- No arbitrary JavaScript execution tool.

### Safety Constraints
- Default headless mode for automated evaluation.
- Explicit timeouts on every browser step.
- Standardized action failure objects instead of raw Playwright stack traces.
- Screenshot path and trace location must stay inside the active workspace.

### Budget Constraints
- Maximum 20 browser steps per acceptance task.
- Maximum 10 seconds per browser action by default.
- Maximum 1 screenshot artifact per step unless explicitly requested by the harness.

## Observation Contract
Every browser step should return a structured observation object with this shape:

```json
{
  "ok": true,
  "url": "http://localhost:8000/search_page.html",
  "title": "Search Demo",
  "action": {
    "kind": "click",
    "target": "button[data-testid='submit']"
  },
  "visible_text": "Search Demo\nQuery\nSearch\nResult A\nResult B",
  "interactive_elements": [
    {
      "tag": "input",
      "text": "",
      "label": "Query",
      "selector_hint": "[data-testid='query']"
    }
  ],
  "artifacts": {
    "screenshot_path": ".miniclaw/browser_runs/run-001/step-003.png"
  },
  "elapsed_ms": 842,
  "error": null
}
```

## Action Contract

### `browser_navigate`
- Input: URL
- Output: page title, URL, visible text summary, artifact path, elapsed time

### `browser_snapshot`
- Input: none
- Output: current page observation without changing state

### `browser_act`
- Allowed actions in Phase 1:
  - `click`
  - `type`
  - `press`
  - `wait`
- Must return a post-action observation

### `browser_extract`
- Allowed extract kinds in Phase 1:
  - `text`
  - `list`
- Returns extracted content plus a small amount of page metadata

### `browser_close`
- Closes the active browser session
- Returns final browser state summary

## Selector Strategy
Phase 1 should prefer deterministic fixture selectors:
- `data-testid`
- stable IDs
- simple CSS selectors

Natural-language element grounding can come later. The first acceptance gate should not depend on fuzzy selector inference.

## Artifact Contract
Each browser task run should persist:
- Run manifest JSON
- Per-step observation JSON
- Per-step screenshot PNG or JPEG
- Final summary JSON

Recommended location:
- `.miniclaw/browser_runs/<run_id>/`

## Acceptance Gate
The feature is considered Phase-1 complete only if the acceptance harness passes the first five deterministic tasks against local fixture pages with:
- 100% task success in local runs
- No raw Playwright exceptions exposed to the model
- Valid artifacts emitted for every step
- Structured observations matching the documented schema

## Open Questions
- Should `browser_extract(list)` support schema hints in Phase 1, or stay text-only?
- Should screenshots be PNG by default for deterministic visual diffs?
- Should the harness persist the browser across tasks or start fresh per task?
