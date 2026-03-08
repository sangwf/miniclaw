# Findings & Decisions

## Requirements
- Install Spec Kit for use with Codex.
- Verify the supported installation path from the official Spec Kit repository.
- Avoid making unnecessary project-level changes in the current empty workspace.

## Research Findings
- Spec Kit is distributed as `specify-cli`, with the recommended install command `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`.
- Spec Kit officially supports Codex as an AI target via `specify init . --ai codex`.
- Spec Kit is not a plain Codex `SKILL.md` repository. It is a CLI that scaffolds project files, slash-command templates, and optional agent skills.
- With `--ai-skills`, Spec Kit installs Codex skills into the project-local `.agents/skills/` directory rather than the global `~/.codex/skills` directory.
- Local environment already has `uv` and `codex` available on PATH.
- `specify-cli` installed successfully as version `0.1.13`.
- The initial `uv` install placed the binary in `~/.local/bin`, which was not yet on PATH.
- Adding `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshenv` makes fresh zsh sessions resolve `specify`.
- `specify check` succeeds and reports `Codex CLI (available)`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Install `specify-cli` globally first | This is the lowest-risk step that actually makes Spec Kit available system-wide |
| Do not run `specify init` in `/Users/sangwf/code/miniclaw` automatically | The current directory is just a planning workspace and not necessarily the user's intended project |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Existing planning files were for a previous comparison task | Replaced them with the current installation task context |
| `~/.local/bin` was not on PATH after installation | Added it to `/Users/sangwf/.zshenv` and verified in a fresh `zsh -lc` session |

## Resources
- Spec Kit repo: https://github.com/github/spec-kit
- Spec Kit README: https://github.com/github/spec-kit/blob/main/README.md
- Spec Kit docs: https://github.github.io/spec-kit/
- Skill installer instructions: /Users/sangwf/.codex/skills/.system/skill-installer/SKILL.md

## Visual/Browser Findings
- Official README shows Codex support and the `specify init . --ai codex` workflow.
