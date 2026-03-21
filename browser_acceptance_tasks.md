# Initial Browser Acceptance Tasks for miniclaw

## Purpose
This task set defines the first deterministic acceptance targets for `miniclaw` browser capability.

## Shared Assumptions
- All tasks run against local fixture pages.
- Fixture pages expose stable `data-testid` selectors.
- Browser actions are bounded by the Phase-1 tool contract.
- Success is judged by final extracted output plus artifact completeness.

## Task 1: Read Simple Page

### ID
`browser_task_001_read_simple_page`

### Fixture
- `fixtures/browser/simple_page.html`

### Goal
Open the page and report the page title plus the main visible body text.

### Expected Interaction Pattern
- `browser_navigate`
- `browser_extract(kind="text")`

### Success Criteria
- Final title exactly matches fixture title.
- Extracted text contains the page heading and body paragraph.
- At least one screenshot artifact exists.

## Task 2: Click a Deterministic Button

### ID
`browser_task_002_click_button`

### Fixture
- `fixtures/browser/click_page.html`

### Goal
Click a button that reveals hidden content, then extract the revealed text.

### Expected Interaction Pattern
- `browser_navigate`
- `browser_snapshot`
- `browser_act(action="click", target="[data-testid='reveal-button']")`
- `browser_extract(kind="text")`

### Success Criteria
- Hidden content is absent before click and present after click.
- Final extracted text contains the revealed message.
- Step count stays at or below 6.

## Task 3: Run a Search Flow

### ID
`browser_task_003_search_flow`

### Fixture
- `fixtures/browser/search_page.html`

### Goal
Type a query into the search box, submit it, and extract the top 3 result labels.

### Expected Interaction Pattern
- `browser_navigate`
- `browser_act(action="type", target="[data-testid='query']", value="apple")`
- `browser_act(action="click", target="[data-testid='submit']")`
- `browser_extract(kind="list")`

### Success Criteria
- Final extracted list contains exactly the expected top 3 items for query `apple`.
- Output order matches fixture order.
- Screenshot artifacts exist for the submit step and final extraction step.

## Task 4: Submit a Form

### ID
`browser_task_004_submit_form`

### Fixture
- `fixtures/browser/form_page.html`

### Goal
Fill two fields, submit the form, and confirm the success message plus echoed values.

### Expected Interaction Pattern
- `browser_navigate`
- `browser_act(action="type", target="[data-testid='name']", value="Welf")`
- `browser_act(action="type", target="[data-testid='email']", value="welf@example.com")`
- `browser_act(action="click", target="[data-testid='submit']")`
- `browser_extract(kind="text")`

### Success Criteria
- Success banner is visible after submit.
- Final extracted text includes both submitted values.
- No action returns a raw executor exception.

## Task 5: Wait for a Deterministic Dynamic Update

### ID
`browser_task_005_wait_for_dynamic_content`

### Fixture
- `fixtures/browser/dynamic_page.html`

### Goal
Trigger a delayed UI update, wait for the new content, and extract the updated state.

### Expected Interaction Pattern
- `browser_navigate`
- `browser_act(action="click", target="[data-testid='load-button']")`
- `browser_act(action="wait", target="[data-testid='loaded-state']")`
- `browser_extract(kind="text")`

### Success Criteria
- The final extracted text includes the post-load content.
- Wait completes within the configured timeout budget.
- Harness trace records the wait step as a first-class action.

## Batch Acceptance Rule
Phase-1 browser capability is considered ready for implementation review when all five tasks pass in the harness with:
- `5/5` success rate
- valid artifacts for every step
- no raw Playwright exceptions exposed as model-facing output
