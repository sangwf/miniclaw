# Task Plan: Install Spec Kit for Codex

## Goal
Install `specify-cli` so Spec Kit is available in the user's Codex environment, verify the installation, and document the project-level step needed to enable Spec Kit commands in a specific repo.

## Current Phase
Phase 4

## Phases
### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify the supported Spec Kit installation path for Codex
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Install Tooling
- [x] Check whether `specify` is already installed
- [x] Install or upgrade `specify-cli`
- [x] Verify the binary is on PATH
- **Status:** complete

### Phase 3: Codex Integration Verification
- [x] Verify Spec Kit recognizes Codex support
- [x] Determine how Codex-specific commands/skills are added to projects
- [x] Capture the limits of a global install vs project initialization
- **Status:** complete

### Phase 4: Delivery
- [x] Summarize what was installed
- [x] State the next command needed in the target project
- [x] Mention any restart/reload requirement if applicable
- **Status:** complete

## Key Questions
1. Is `spec-kit` a Codex skill, or a CLI that scaffolds Codex-specific commands?
2. What can be installed globally right now without guessing the target project?
3. What exact command should the user run inside a project to enable `/speckit.*` for Codex?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat `spec-kit` as a CLI-based workflow, not a native `SKILL.md` repo | Its README centers on `specify init` and project templates rather than a standalone Codex skill |
| Install the global CLI but avoid initializing the current empty workspace as a Spec Kit project | The user asked to install Spec Kit in Codex, not to convert `/Users/sangwf/code/miniclaw` into a Spec Kit project |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `specify --version` failed because the CLI uses a subcommand form | 1 | Switched to `uv tool list`, `specify --help`, and `specify check` for verification |

## Notes
- Keep the distinction clear between global CLI install and project-local Codex command setup.
