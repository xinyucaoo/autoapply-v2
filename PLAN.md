# Autoapply V2 — Implementation Plan

## Context

Build a system that automates job applications given a URL. The user creates/maintains a profile, then says "apply to \<url\>" and Claude Code orchestrates browser-use CLI to fill the application form intelligently. **No LLM API calls** — Claude Code IS the AI brain. Browser automation is purely via `browser-use` CLI commands.

**Design philosophy:** The CLI and Python code handle deterministic logic (field resolution, answer policies, data management). The SKILL.md makes Claude Code the orchestrator — it calls into the resolver engine, respects answer policies, and only uses its own NLU judgment as a fallback. This keeps the system testable, reproducible, and safe.

**Tech stack: Python** — same ecosystem as browser-use, enabling future direct library integration. Publishable as a pip package, Claude Code skill, or MCP server.

---

## Architecture: Hybrid (CLI + Resolver Engine + Skill)

- **`autoapply` CLI** (Python, Click) — profile CRUD, history management, field resolution
- **Resolver engine** (`resolver.py`) — deterministic field→answer mapping with confidence levels and answer policies
- **`skills/autoapply/SKILL.md`** — Claude Code orchestration: calls resolver, handles browser-use, prompts user
- **`browser-use` CLI** — browser automation (navigate, read state, fill fields, click, screenshot)
- **Data storage** — local JSON files in `~/.autoapply/` (behind a service interface for future swap to SQLite)

```
autoapply-v2/
├── skills/
│   └── autoapply/
│       └── SKILL.md                  # Application workflow skill for Claude Code
├── src/
│   └── autoapply/
│       ├── __init__.py
│       ├── cli.py                    # Click CLI entry point
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── profile.py            # profile show/set/add/remove/init/import/export
│       │   ├── history.py            # history list/show/search/lookup/add
│       │   └── resolve.py            # resolve <field_label> [--type] [--options] [--company]
│       ├── models/
│       │   ├── __init__.py
│       │   ├── profile.py            # Profile Pydantic model
│       │   └── history.py            # History Pydantic model
│       ├── services/
│       │   ├── __init__.py
│       │   ├── profile_store.py      # Read/write/validate profile.json
│       │   ├── history_store.py      # Read/write/query history.json
│       │   └── resolver.py           # Field resolution engine
│       └── config.py                 # Paths, constants (~/.autoapply/)
├── tests/
│   ├── conftest.py
│   ├── test_profile_store.py
│   ├── test_history_store.py
│   └── test_resolver.py
├── pyproject.toml
├── .gitignore
└── CLAUDE.md
```

---

## Resolver Engine (`resolver.py`)

The core improvement: a deterministic resolution pipeline that Claude Code calls via CLI before using its own judgment.

### Resolution Order
1. **Canonical mapping** — exact match of normalized field label to profile path (e.g., "first name" → `personal.first_name`). High confidence.
2. **Alias mapping** — known aliases (e.g., "legal given name", "given name", "nombre" → `personal.first_name`). High confidence.
3. **Scoped history match** — find previous answer for this normalized question, scoped by company + matching option set. Medium confidence.
4. **No match** — return `null`, signaling Claude Code to either infer or ask the user.

### CLI Command
```
autoapply resolve "<field_label>" [--type text|select|...] [--options "opt1,opt2,..."] [--company "Acme"]
```

Returns JSON:
```json
{
  "answer": "John",
  "source": "profile",
  "profile_path": "personal.first_name",
  "confidence": "high",
  "policy": "autofill"
}
```

Or when no match / policy prevents autofill:
```json
{
  "answer": "Male",
  "source": "profile",
  "confidence": "high",
  "policy": "suggest_only",
  "suggestion": "Male (from profile EEO data)"
}
```

Or when nothing found:
```json
{
  "answer": null,
  "source": null,
  "confidence": null,
  "policy": "ask_user"
}
```

### Canonical Field Map (in code, testable)
~60 entries covering common form fields:
- `first name`, `given name`, `legal first name` → `personal.first_name`
- `email`, `email address`, `e-mail` → `personal.email`
- `phone`, `mobile`, `telephone`, `phone number` → `personal.phone`
- `linkedin`, `linkedin url`, `linkedin profile` → `personal.linkedin_url`
- `authorized to work`, `work authorization`, `legally authorized` → `work_authorization.authorized_us`
- `sponsorship`, `visa sponsorship`, `require sponsorship` → `work_authorization.sponsorship_needed`
- `gender` → `eeo.gender` (policy: `suggest_only`)
- `race`, `ethnicity` → `eeo.race_ethnicity` (policy: `suggest_only`)
- `salary`, `expected salary`, `desired compensation` → `salary.desired` (policy: `always_prompt`)
- etc.

---

## Answer Policies

Each profile field has an associated fill policy:

| Policy | Behavior |
|--------|----------|
| `autofill` | Fill automatically without asking. Default for personal info, work auth, education. |
| `suggest_only` | Show value to user with suggestion, but require confirmation. For EEO, demographics. |
| `always_prompt` | Always ask the user, even if profile has the data. For salary, start date, relocation. |
| `never_store` | Prompt every time, never save to history. For sensitive fields like SSN, criminal history. |

Default policies (configurable in profile):
```python
DEFAULT_POLICIES = {
    "personal.*": "autofill",
    "work_authorization.*": "autofill",
    "education.*": "autofill",
    "experience.*": "autofill",
    "skills": "autofill",
    "resume_path": "autofill",
    "eeo.*": "suggest_only",
    "salary.*": "always_prompt",
    "cover_letter": "suggest_only",
}
```

Users can override in profile:
```json
{
  "answer_policies": {
    "work_authorization.sponsorship_needed": "always_prompt",
    "salary.*": "never_store"
  }
}
```

---

## Data Models

### Profile (`~/.autoapply/profile.json`)

```python
class Document(BaseModel):
    name: str                     # "default_resume", "swe_resume", etc.
    path: str                     # Absolute path to file
    type: Literal["resume", "cover_letter", "transcript", "other"]
    default: bool = False

class Personal(BaseModel):
    first_name: str
    last_name: str
    preferred_name: str | None = None
    pronouns: str | None = None
    email: str
    phone: str
    address: Address
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    github_url: str | None = None

class WorkAuthorization(BaseModel):
    authorized_us: bool
    sponsorship_needed: bool
    citizenship: str
    visa_status: str | None = None

class Education(BaseModel):
    school: str
    degree: str
    field: str
    graduation_date: str          # "2020-05" (YYYY-MM)
    gpa: str | None = None

class Experience(BaseModel):
    company: str
    title: str
    start_date: str               # "2020-06" (YYYY-MM)
    end_date: str | None = None   # None = current
    description: str
    location: str | None = None

class EEO(BaseModel):
    gender: str | None = None
    race_ethnicity: str | None = None
    veteran_status: str | None = None
    disability_status: str | None = None

class CustomQA(BaseModel):
    question: str                 # Pattern to match against form field labels
    answer: str
    scope: str | None = None      # Optional: limit to company/role
    policy: str = "autofill"      # autofill, suggest_only, always_prompt

class Salary(BaseModel):
    minimum: int | None = None
    desired: int | None = None
    currency: str = "USD"

class Preferences(BaseModel):
    remote_preference: str | None = None        # "remote", "hybrid", "onsite"
    relocation_willing: bool | None = None
    desired_start_date: str | None = None
    years_of_experience: int | None = None

class Profile(BaseModel):
    personal: Personal
    work_authorization: WorkAuthorization
    education: list[Education] = []
    experience: list[Experience] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    eeo: EEO | None = None
    documents: list[Document] = []              # Multiple resumes, cover letters
    cover_letter: str | None = None             # Default cover letter text
    custom_qa: list[CustomQA] = []
    salary: Salary | None = None
    preferences: Preferences | None = None
    answer_policies: dict[str, str] = {}        # Override default policies
```

### Application History (`~/.autoapply/history.json`)

```python
class QAPair(BaseModel):
    field_label: str              # Original label as shown on page
    normalized_key: str | None    # Canonical key from resolver (e.g., "personal.first_name")
    field_type: str               # text, select, radio, checkbox, textarea, file
    answer: str
    options: list[str] | None = None
    source: Literal["profile", "history", "user", "inference"]
    company: str | None = None
    user_verified: bool = False   # True if user confirmed/provided this answer

class ApplicationRecord(BaseModel):
    id: str                       # UUID
    url: str
    company: str
    job_title: str
    applied_at: str               # ISO 8601
    status: Literal["in_progress", "submitted", "failed", "withdrawn"]
    qa_pairs: list[QAPair] = []

class ApplicationHistory(BaseModel):
    applications: list[ApplicationRecord] = []
```

---

## CLI Commands (`autoapply`)

Installed via `pip install -e .` → registers `autoapply` console script.

### Profile
```
autoapply profile show [section]              # Show full profile or a section
autoapply profile set <dotpath> <value>       # Set field: profile set personal.email "j@x.com"
autoapply profile add <array-path> '<json>'   # Append to array
autoapply profile remove <array-path> <index> # Remove from array by index
autoapply profile init                        # Scaffold empty profile.json
autoapply profile import <file>               # Import from JSON file
autoapply profile export [file]               # Export (stdout or file)
```

### History
```
autoapply history list                        # List all applications
autoapply history show <id>                   # Show full record with Q&A
autoapply history search <query>              # Search Q&A pairs by question text
autoapply history lookup <question> [--company] [--verified-only]
autoapply history add '<json>'                # Add full application record
autoapply history stats                       # Summary counts
```

### Resolve (new — used by SKILL.md)
```
autoapply resolve "<field_label>" [--type text|select|...] [--options "opt1,opt2,..."] [--company "Acme"]
```

---

## SKILL.md — Application Workflow

The skill instructs Claude Code as the **orchestrator**, not the brain. Core logic lives in the resolver.

### Workflow Steps
1. **Load profile** via `autoapply profile show`
2. **Check history** via `autoapply history search "<company>"`
3. **Open job page** via `browser-use --headed open "<url>"`
4. **Navigate to form** — find and click "Apply" buttons
5. **Scan form fields** — `browser-use state` to get numbered elements
6. **For each field, call the resolver:**
   ```
   autoapply resolve "<field label>" --type select --options "opt1,opt2" --company "Acme"
   ```
   - If `policy=autofill` and `confidence=high` → fill automatically
   - If `policy=suggest_only` → present suggestion, ask user to confirm
   - If `policy=always_prompt` → always ask, show suggestion if available
   - If `answer=null` → Claude Code may infer from profile context, or ask user
7. **Batch unresolved questions** — collect all unresolved fields on a page, present them together:
   ```
   I need answers for 3 fields on this page:

   1. "How many years of experience in a related role?"
      Options: [1] Less than 1  [2] 1-3  [3] 3-5  [4] 5-10  [5] 10+
      [Suggested: [4] 5-10 — based on experience starting 2020-06]

   2. "Desired salary range"
      [No suggestion — always_prompt policy]

   3. "How did you hear about us?"
      Options: [1] LinkedIn  [2] Referral  [3] Company website  [4] Job board  [5] Other
   ```
8. **Handle multi-page forms** — click Next/Continue, repeat scan+fill+batch
9. **Review before submit** — present summary of all filled fields, get user confirmation
10. **Record application** — `autoapply history add '<json>'` with all Q&A pairs including `normalized_key`, `company`, and `user_verified` flags

### Field Mapping Reference (in SKILL.md)
A reference table for Claude Code's fallback inference when resolver returns no match. 30+ common patterns.

---

## Key Files

| File | Purpose |
|------|---------|
| `skills/autoapply/SKILL.md` | Orchestration workflow for Claude Code |
| `src/autoapply/services/resolver.py` | **Core logic**: field resolution with canonical map, aliases, history, policies |
| `src/autoapply/cli.py` | Click CLI entry point |
| `src/autoapply/models/profile.py` | Pydantic profile model with policies and documents |
| `src/autoapply/models/history.py` | Pydantic history model with scoped Q&A |
| `src/autoapply/services/profile_store.py` | Profile CRUD with JSON file I/O |
| `src/autoapply/services/history_store.py` | History CRUD + scoped Q&A lookup |
| `src/autoapply/commands/resolve.py` | `autoapply resolve` CLI command |
| `src/autoapply/commands/profile.py` | Profile CLI subcommands |
| `src/autoapply/commands/history.py` | History CLI subcommands |
| `pyproject.toml` | Package config, deps (pydantic, click), scripts entry |
| `CLAUDE.md` | Project instructions and commands |

---

## Implementation Phases

### Phase 1: Project Setup + Data Layer
- `pyproject.toml` (deps: pydantic, click; dev-deps: pytest), `.gitignore`
- Pydantic models for Profile (with documents, preferences, answer_policies) and ApplicationHistory (with scoped QAPair)
- `profile_store.py` — read/write/validate `~/.autoapply/profile.json`
- `history_store.py` — read/write/query with scoped lookup
- `config.py` — paths, defaults
- Tests for both stores

### Phase 2: Resolver Engine
- `resolver.py` — canonical field map (~60 entries), alias normalization, history lookup, policy enforcement
- `commands/resolve.py` — CLI command wrapping the resolver
- `test_resolver.py` — test canonical matches, aliases, policy enforcement, edge cases

### Phase 3: CLI
- Click CLI entry point with group commands
- Profile subcommands (show, set, add, remove, init, import, export)
- History subcommands (list, show, search, lookup, add, stats)
- `pip install -e .` so `autoapply` command works

### Phase 4: Skill Definition
- Write `skills/autoapply/SKILL.md` with workflow, batched prompting format, field mapping reference
- Update `CLAUDE.md` with project instructions and commands
- Update `.claude/settings.local.json` permissions if needed

### Phase 5: End-to-End Testing
- Test full workflow with a real job URL
- Iterate on SKILL.md and resolver based on real behavior
- Add resolver entries for any common fields missed
- Validate that answer policies prevent unsafe autofills

---

## Verification

1. **Unit tests**: `pytest` — profile-store, history-store, and resolver tests pass
2. **Resolver tests**: canonical mapping covers 60+ field labels; policies correctly enforce suggest_only/always_prompt; scoped history returns correct answers
3. **CLI smoke test**: `autoapply profile init` creates valid profile.json; `autoapply resolve "first name"` returns correct answer
4. **Profile CRUD**: set/show/add/remove operations work correctly
5. **History operations**: add records, scoped search, lookup with company filter
6. **E2E**: Invoke the skill with a real job URL, verify:
   - Resolver handles known fields automatically
   - Sensitive fields prompt with suggestion (not autofill)
   - Unknown fields are batched and presented clearly
   - Review summary shown before submission
   - Application recorded to history with normalized keys
