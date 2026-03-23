# CLAUDE.md

## Project: autoapply-v2

Automated job application system. Claude Code orchestrates browser-use to fill application forms intelligently using the user's profile.

## Setup

```bash
uv sync --dev
uv run autoapply profile init
```

## Browser Automation

`browser-use` is a Python tool installed via `uvx`. Always invoke it as:

```bash
uvx browser-use state
uvx browser-use --headed open <url>
uvx browser-use click <index>
# etc.
```

Do NOT use `browser-use`, `npx browser-use`, or any other invocation — only `uvx browser-use`.

## Development Commands

```bash
uv run pytest                          # Run all tests
uv run pytest tests/test_resolver.py  # Run resolver tests only
uv run autoapply --help               # CLI help
uv run autoapply profile show         # View current profile
uv run autoapply profile init         # Create empty profile
uv run autoapply resolve "first name" # Test resolver (single field)
uv run autoapply resolve-batch --ats workday --fields '[{"label":"state","type":"combobox"}]'  # Batch resolver with ATS + recipe
uv run autoapply fill-prep --state /tmp/state.txt --resolver /tmp/resolver.json  # Build fill engine input
uvx browser-use python --file scripts/fill_engine.py  # Run fill engine
uv run autoapply history list         # View application history
uv run autoapply history stats        # Application statistics
```

## Architecture

- `src/autoapply/services/resolver.py` — Core field resolution engine (deterministic label -> profile value mapping)
- `src/autoapply/models/profile.py` — Pydantic v2 Profile model (personal, work auth, education, experience, EEO, salary, preferences, documents)
- `src/autoapply/models/history.py` — Pydantic v2 ApplicationHistory model with scoped QAPairs
- `src/autoapply/services/profile_store.py` — Profile CRUD with dot-path get/set and JSON file I/O
- `src/autoapply/services/history_store.py` — History CRUD + scoped Q&A lookup
- `src/autoapply/commands/profile.py` — `autoapply profile` CLI subcommands
- `src/autoapply/commands/history.py` — `autoapply history` CLI subcommands
- `src/autoapply/commands/resolve.py` — `autoapply resolve` CLI command
- `src/autoapply/commands/fill_engine.py` — `autoapply fill-prep` CLI command
- `src/autoapply/services/fill_prep.py` — Parses browser-use state + builds fill engine input JSON
- `src/autoapply/services/playbooks.py` — Per-ATS widget interaction recipes
- `scripts/fill_engine.py` — Self-contained fill script (runs inside browser-use python session)
- `src/autoapply/cli.py` — Click CLI entry point
- `src/autoapply/config.py` — Paths and constants (respects AUTOAPPLY_DIR env var)
- `skills/autoapply/SKILL.md` — Claude Code application workflow skill
- Data stored in `~/.autoapply/` (gitignored)
  - `profile.json` — user profile
  - `history.json` — application history
  - `sessions/<ats>.json` — browser login cookies per ATS platform (e.g. `sessions/workday.json`)

## Using the Skill

When the user says "apply to <url>", load the `autoapply` skill and follow the workflow in `skills/autoapply/SKILL.md`.

## Key Design Decisions

- **Resolver resolution order**: canonical map → custom Q&A → history → ask_user
- **Answer policies**: `autofill` (personal/work auth/education), `suggest_only` (EEO), `always_prompt` (salary/start date), `ask_user` (unknown)
- **Data storage**: JSON files in `~/.autoapply/` behind service interfaces (easy to swap to SQLite)
- **Test isolation**: `AUTOAPPLY_DIR` env var redirects all I/O to a temp directory during tests
- **Dot-path addressing**: `personal.address.city`, `education.0.school` etc. for deep field access
