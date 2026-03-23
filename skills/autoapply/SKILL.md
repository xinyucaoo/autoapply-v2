---
name: autoapply
description: >
  Automates job applications by reading the user's profile, navigating to
  job application pages with browser-use, intelligently filling form fields
  using a deterministic resolver engine, and tracking application history.
  Use when the user says "apply to <url>", "submit this application", or similar.
allowed-tools: Bash(browser-use:*),Bash(autoapply:*),Bash(python3:*)
---

# autoapply Skill — Application Workflow

This skill orchestrates the end-to-end job application process. You (Claude Code) are the
orchestrator. All deterministic field resolution happens in the `autoapply` CLI — use your
own judgment only as a fallback for fields the resolver cannot answer.

**Speed principle:** Minimize LLM round-trips. Use batch operations everywhere possible.
Each page should take ~8-10 tool calls total, not 50+.

---

## Step 1: Prerequisites + Context Load

Load profile and history in a single step:

```bash
autoapply profile show && autoapply history search "<company name>"
```

Note the company name and job title. If profile is empty or missing, stop and tell the user:
> "No profile found. Run `autoapply profile init` and fill in your details before applying."

---

## Step 2: Open the Job Page

```bash
uvx browser-use --headed open "<url>"
```

Import saved session cookies if they exist (silently skip if not):

```bash
[ -f ~/.autoapply/sessions/<ats>.json ] && uvx browser-use --headed cookies import ~/.autoapply/sessions/<ats>.json
```

Then reload to apply cookies:

```bash
uvx browser-use --headed eval "window.location.reload()"
```

Get state (not screenshot) to find the Apply button:

```bash
uvx browser-use state
```

Click Apply and navigate to the application form:

```bash
uvx browser-use click <index>
```

---

## Step 3: Fill Each Application Page

**Target: ~5 tool calls per page** (not 30+)

### 3A: Scan page

```bash
uvx browser-use state > /tmp/page_state.txt && cat /tmp/page_state.txt
```

Read the output and identify:
- All form fields (labels, element IDs, widget types)
- Which fields are required (`required=true`)
- The Save/Continue button index
- Any **expandable sections** — buttons or links like "Add Work Experience", "Add Education", "+ Add", "Add another" etc.

**If expandable sections exist, click them all before resolving:**

```bash
uvx browser-use click <add_work_experience_idx>
# repeat for each "Add" button on the page
uvx browser-use state > /tmp/page_state.txt && cat /tmp/page_state.txt
```

Re-read state after expanding so the sub-fields (Company, Title, Start Date, etc.) are visible before resolve-batch runs.

### 3B: Resolve all fields

Build a JSON array of all visible fields with their labels and widget types, then resolve:

```bash
uv run autoapply resolve-batch --ats <ats> --company "<company>" --fields '<fields_json>' > /tmp/resolver_output.json
```

### 3C: Collect user input for PROMPT fields

Read `/tmp/resolver_output.json`. For fields with `policy: "suggest_only"`, `"always_prompt"`, or `"ask_user"`, ask the user in a single batch message before proceeding.

After receiving answers, update the resolver output JSON with the user's answers.

### 3D: Build fill engine input + fill all fields

```bash
# Build fill engine input (auto-maps labels to DOM elements)
uv run autoapply fill-prep \
  --state /tmp/page_state.txt \
  --resolver /tmp/resolver_output.json \
  --ats <ats> \
  --output /tmp/autoapply_fill_input.json

# Run fill engine (fills everything deterministically)
uvx browser-use python --file scripts/fill_engine.py

# Check results
cat /tmp/autoapply_fill_output.json
```

### 3E: Handle failures and special fields

Read the fill output. For any `"status": "failure"`, `"error"`, or `"manual_required"` fields:
- **Radio buttons**: Use JS via `uvx browser-use eval` to find and click the correct radio
- **Date segmented**: Find the segment indices from state and fill with `browser.keys()`
- **Unknown fields**: Ask the user, then use `uvx browser-use input <idx> <value>` or `browser.type()`

**Note:** Fields auto-matched by `fill-prep` but with wrong mapping will show as failures. Re-check the state text and manually fill those fields.

### 3F: Pre-navigation validation

Before clicking Save/Continue:
1. Check fill output for any failures
2. Run `uvx browser-use state` and scan for `Error` text, `Select One` in required fields, `MM`/`YYYY` placeholders
3. Fix any issues
4. Click Save/Continue and verify new page loaded (not same page with `Errors Found`)

**EEO fields** (gender, race, veteran, disability) have `autofill` policy — they fill automatically from profile via the fill engine without prompting.

---

## Step 4: Pre-Submission Review

Before clicking Submit, compile a summary table and present to user:

```
Ready to submit your application to Acme Corp — Senior Engineer.

PERSONAL
  First Name:           Jane
  Last Name:            Doe
  Email:                jane@example.com
  Phone:                555-123-4567

WORK AUTHORIZATION
  Authorized (US):      Yes
  Sponsorship needed:   No

EDUCATION
  School:               MIT | Degree: Bachelor of Science | GPA: 3.8

CUSTOM / USER-PROVIDED
  Why interested:       I'm passionate about distributed systems.
  Expected salary:      180000 (you confirmed)
  Gender:               Female (you confirmed)

Shall I submit? (yes / no / edit <field>)
```

Wait for "yes" before clicking Submit.

---

## Step 5: Submit

```bash
uvx browser-use click <submit_button_index>
```

Wait for confirmation page. Take a screenshot to confirm success.

---

## Step 6: Record the Application

```bash
autoapply history add '{
  "id": "<uuid4>",
  "url": "<job_url>",
  "company": "<company>",
  "job_title": "<title>",
  "applied_at": "<ISO8601>",
  "status": "submitted",
  "qa_pairs": [...]
}'
```

Generate UUID and timestamp:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())"
```

---

## Operational Tips

- **Never take screenshots during form filling** — always use `uvx browser-use state` for debugging. Screenshots are only for post-submit confirmation (Step 5).
- **Always invoke browser-use as `uvx browser-use`** (it's a Python tool, not npm). Never use `browser-use` or `npx browser-use`.
- **Always use `--headed`** so the user can see the browser in real time.
- **Batch is the default** — only fall back to individual commands for tricky fields that fail.
- **Workday shadow DOM**: Inputs are often inside shadow roots. If `browser-use input <idx>` fails,
  use `browser-use eval` with `findInShadow()` or click by pixel coordinates.
- **ReactVirtualized dropdowns** (Workday field-of-study etc.): They don't filter on fill/type.
  Click the field to open it, then use `browser-use keys` to type character by character,
  then press `Enter` to filter, then click the matching option from state output.
- **Date fields**: Click the month/day/year segments individually and use `browser-use keys` to type digits.
- **CAPTCHA**: Tell user "A CAPTCHA appeared — please solve it, then let me know to continue."
- **Page reload**: `browser-use eval "window.location.reload()"`
- **Scroll to reveal hidden fields**: `browser-use scroll down`
- **If batch fill partially fails**: The python script prints ERR lines — fix only those fields
  individually, don't re-run the whole batch.
- **File uploads**: `browser-use upload <index> "<absolute_path>"`
  Get path from: `autoapply profile show documents`

---

## Field Mapping Reference

When the resolver returns `answer: null`, use this table for Claude Code's fallback inference.
Always present inferred answers as suggestions — never autofill unresolved fields.

| Form Field Pattern | Profile Path | Notes |
|---|---|---|
| first name, given name, legal first name | personal.first_name | |
| last name, surname, family name | personal.last_name | |
| full name, legal name | personal.first_name + " " + personal.last_name | Combine |
| email, e-mail | personal.email | |
| phone, mobile, cell, telephone | personal.phone | |
| street address, address line 1 | personal.address.street | |
| city | personal.address.city | |
| state, province | personal.address.state | |
| zip, postal code | personal.address.zip | |
| country | personal.address.country | |
| linkedin url | personal.linkedin_url | |
| github | personal.github_url | |
| website, portfolio | personal.portfolio_url | |
| authorized to work in US | work_authorization.authorized_us | Yes/No |
| require sponsorship | work_authorization.sponsorship_needed | Yes/No |
| citizenship | work_authorization.citizenship | |
| visa status | work_authorization.visa_status | |
| school, university | education.0.school | Most recent |
| degree | education.0.degree | |
| field of study, major | education.0.field | |
| graduation date | education.0.graduation_date | YYYY-MM |
| GPA | education.0.gpa | |
| current company, employer | experience.0.company | Most recent |
| job title, position | experience.0.title | |
| gender | eeo.gender | suggest_only |
| race, ethnicity | eeo.race_ethnicity | suggest_only |
| veteran status | eeo.veteran_status | suggest_only |
| disability status | eeo.disability_status | suggest_only |
| salary, expected salary | salary.desired | always_prompt |
| start date | preferences.desired_start_date | always_prompt |
| remote preference | preferences.remote_preference | |
| willing to relocate | preferences.relocation_willing | suggest_only |
| years of experience | preferences.years_of_experience | |
