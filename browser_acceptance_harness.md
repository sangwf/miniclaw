# Browser Acceptance Harness for miniclaw

## Purpose
Define the harness used to evaluate browser capability before and during implementation. The harness is the contract that implementation must satisfy.

## Harness Goal
Provide a deterministic, replayable browser test environment that can answer one question clearly:

Can `miniclaw` complete the intended Phase-1 browser tasks through a bounded tool interface with reliable observations and artifacts?

## Why Harness-First
Without a harness, browser work tends to drift into ad hoc demos. This harness prevents that by fixing:
- Task inputs
- Allowed environment
- Constraints
- Observations
- Success criteria
- Artifact requirements

## Harness Components

### 1. Fixture Pages
Local static or lightly dynamic pages under:
- `fixtures/browser/`

Recommended first fixture set:
- `fixtures/browser/simple_page.html`
- `fixtures/browser/click_page.html`
- `fixtures/browser/search_page.html`
- `fixtures/browser/form_page.html`
- `fixtures/browser/dynamic_page.html`

These pages should be deterministic and contain stable `data-testid` attributes.

### 2. Local Test Server
Serve fixtures on localhost during harness runs.

Recommended shape:
- `python3 -m http.server <port>` in `fixtures/browser/`
- or a tiny dedicated Python server script if dynamic endpoints are needed

### 3. Harness Runner
The runner should:
- Start fixture server
- Start browser runtime
- Execute one acceptance task at a time
- Record all actions and observations
- Judge pass/fail
- Write artifacts to disk

Recommended location:
- `scripts/browser_harness.py`

### 4. Artifact Store
Each run should create:
- `.miniclaw/browser_runs/<run_id>/manifest.json`
- `.miniclaw/browser_runs/<run_id>/steps/<step_n>.json`
- `.miniclaw/browser_runs/<run_id>/steps/<step_n>.png`
- `.miniclaw/browser_runs/<run_id>/result.json`

### 5. Verifier
The verifier should judge:
- Was the target action sequence completed?
- Did the extracted result match the expectation?
- Did all required artifacts exist?
- Did the observation schema remain valid?

## Harness Modes

### Development Mode
- Headed browser optional
- Full screenshots
- Verbose logs
- Single-task execution

### CI/Regression Mode
- Headless browser
- Deterministic viewport
- Fixed timeout budget
- Batch execution over all acceptance tasks

## Environment Contract
- Browser backend: Playwright Chromium
- Viewport: fixed, e.g. `1280x900`
- Locale: stable default locale
- Timezone: fixed test timezone when needed
- Network: localhost fixture pages only for acceptance tasks
- Output root: workspace-local `.miniclaw/browser_runs/`

## Step Contract
Each harness step must record:
- `step_index`
- `requested_action`
- `normalized_action`
- `pre_url`
- `post_url`
- `title`
- `visible_text`
- `interactive_elements`
- `elapsed_ms`
- `ok`
- `error`
- `screenshot_path`

## Allowed Failure Modes
These are acceptable harness outputs:
- Selector not found
- Timeout waiting for deterministic state change
- Unexpected page title
- Missing expected extracted item

These are not acceptable:
- Uncaught Playwright exception dumped raw to the model
- Missing artifact directory
- Invalid observation shape
- Browser process left hanging after run

## Success Criteria
A task passes only if:
- The final extracted value matches the task contract
- The step count stays within budget
- Every step produces a valid observation
- The final run summary contains `ok: true`

## Metrics to Track
For each task:
- `success`
- `step_count`
- `elapsed_ms_total`
- `extract_correct`
- `artifact_complete`

For the whole batch:
- pass rate
- mean steps per task
- mean runtime
- top failure categories

## Progressive Rollout Plan

### Gate 1
Local deterministic fixtures only.

### Gate 2
Slightly more dynamic local fixtures.

### Gate 3
Limited public-web smoke tasks that are not used as the primary acceptance gate.

## Implementation Notes
- The harness runner should be usable without the full LLM loop.
- It should be possible to feed scripted action sequences directly for executor debugging.
- The same harness should later be reusable for agent-driven rollouts.

## Deliverables Expected Before Implementation
- Feature spec
- Harness spec
- Acceptance task set
- Fixture page plan
- Artifact schema

## Definition of Done for the Planning Phase
Planning is complete once:
- The feature spec is written
- The harness design is written
- The first batch of acceptance tasks is written
- The fixture requirements are explicit enough that implementation can start without redefining success
