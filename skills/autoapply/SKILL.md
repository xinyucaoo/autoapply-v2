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

**Detect ATS platform from the URL** (no extra tool call needed — just inspect the URL string):
- `myworkdayjobs.com` or `wd*.myworkday*` → `workday`
- `greenhouse.io` or `boards.greenhouse` → `greenhouse`
- `lever.co` or `jobs.lever` → `lever`
- `icims.com` → `icims`
- Unknown → omit `--ats` flag

Store this as `<ats>` and pass it to all `resolve-batch` calls in Step 3B.

**Import stored session cookies** (if a saved session exists for this ATS):

```bash
uvx browser-use --headed open "<url>" && uvx browser-use cookies import ~/.autoapply/sessions/<ats>.json
```

If no session file exists yet, skip the import — just open the page:

```bash
uvx browser-use --headed open "<url>"
```

Get state to see if login is needed:

```bash
uvx browser-use state
```

**If a login page appears**: Tell the user "Please log in, then let me know to continue." Wait for the user to log in. Once they confirm, **immediately save the session**:

```bash
mkdir -p ~/.autoapply/sessions && uvx browser-use cookies export ~/.autoapply/sessions/<ats>.json
```

This session will be reused on all future applications to the same ATS, skipping the login step entirely.

Click Apply and navigate to the application form:

```bash
uvx browser-use click <index>
```

---

## Step 3: Per-Page Batch Workflow

Repeat this workflow for **each page** of the application form.

### 3A: Scan the page

```bash
uvx browser-use state
```

From the state output, identify ALL form fields on the current page:
- Their element indices
- Their labels / aria-labels
- Their **widget type** — critical for recipe selection:
  - `text` / `textarea` — standard text input
  - `select` — native HTML `<select>` dropdown
  - `combobox` — custom combo-box with `role="combobox"`, or any Workday dropdown that isn't a native `<select>` (state, country, degree, "how did you hear about us?", etc.)
  - `radio` — radio button group
  - `checkbox` — checkbox
  - `file` — file upload
  - `date_segmented` — date with separate month/day/year segments (Workday)
  - `react_virtualized` — Workday ReactVirtualized list (field-of-study etc.)
- Available options for selects/radios/comboboxes

### 3B: Batch resolve ALL fields at once

Build a single JSON array of all fields and call the resolver once, **passing `--ats <ats>`**:

```bash
uv run autoapply resolve-batch --ats workday --company "<company>" --fields '[
  {"label": "First Name", "type": "text"},
  {"label": "Email", "type": "text"},
  {"label": "State", "type": "combobox"},
  {"label": "Work Authorization", "type": "combobox", "options": ["Yes", "No"]},
  {"label": "How did you hear about us?", "type": "combobox", "options": ["LinkedIn", "Referral", "Other"]},
  {"label": "Gender", "type": "select", "options": ["Male", "Female", "Decline to State"]}
]'
```

This returns a JSON array — one result per field. **Each result may include an `interaction_recipe`** that tells you exactly how to fill the field, eliminating trial-and-error.

### 3C: Classify fields by policy

Split the resolved fields into two groups:

**AUTOFILL** (policy=`autofill`, confidence=`high`) — fill without asking.

**PROMPT** (policy=`suggest_only`, `always_prompt`, or `ask_user`) — collect and ask user.

### 3D: Batch fill autofill fields using interaction recipes

**If `interaction_recipe` is present** in the resolver output for a field, follow its steps exactly — substitute `{idx}` with the actual element index and `{answer}` with the resolved answer. Do NOT try other approaches first.

**Recipe widget types and how to execute them:**

**`combobox`** (Workday state, country, degree, "how did you hear", etc.):
```bash
uvx browser-use python "
import time
combos = [
    (42, 'Illinois'),   # State
    (55, 'LinkedIn'),   # How did you hear about us?
]
results = []
for idx, val in combos:
    try:
        browser.click(idx)      # Step 1: open combo box
        time.sleep(0.3)
        browser.type(val)       # Step 2: type to filter
        time.sleep(0.5)
        browser.keys('Enter')   # Step 3: select top match
        time.sleep(0.3)
        results.append(f'OK: [{idx}]={val!r}')
    except Exception as e:
        results.append(f'ERR: [{idx}] {e}')
print('\n'.join(results))
"
```

**`react_virtualized`** (Workday field-of-study — does NOT respond to type, must use keys):
```bash
uvx browser-use python "
import time
browser.click(63)               # open the dropdown
time.sleep(0.4)
browser.keys('C')               # type char by char via keys
time.sleep(0.1)
browser.keys('o')
# ... continue for full value
time.sleep(0.6)
"
# then: uvx browser-use state → find matching option index → uvx browser-use click <idx>
```

**`date_segmented`** (Workday start date, graduation date — separate month/day/year inputs):
```bash
uvx browser-use python "
import time
browser.click(71)           # month segment
time.sleep(0.2)
browser.keys('05')          # type MM
time.sleep(0.2)
browser.click(72)           # day segment
time.sleep(0.2)
browser.keys('01')          # type DD
time.sleep(0.2)
browser.click(73)           # year segment
time.sleep(0.2)
browser.keys('2026')        # type YYYY
"
```

**`select`** (native HTML select):
```bash
uvx browser-use python "
import time
selects = [
    (28, 'Female'),     # Gender
]
for idx, option in selects:
    browser.click(idx)
    time.sleep(0.2)
    browser.select(idx, option)
"
```

**`radio`**: click the radio button index whose label matches the answer.

**`text` / `textarea`** (no recipe needed — use standard batch fill):
```bash
uvx browser-use python "
fields = [
    (3, 'Xinyu'),
    (4, 'Cao'),
    (5, 'xinyucao@example.com'),
    (7, '5551234567'),
]
results = []
for idx, val in fields:
    try:
        browser.input(idx, val)
        results.append(f'OK: [{idx}]={val!r}')
    except Exception as e:
        results.append(f'ERR: [{idx}] {e}')
print('\n'.join(results))
"
```

**If `interaction_recipe` is null** and the field is a select/combobox, fall back to: click to open → `browser.select(idx, option)`. If that fails, use the combobox pattern (click → type → Enter).

### 3E: Take a single verification screenshot

After batch filling autofill fields:

```bash
uvx browser-use screenshot
```

### 3G: Batch prompt user for non-autofill fields

If there are any PROMPT fields (suggest_only, always_prompt, ask_user), present them ALL together
in a single numbered list before filling any of them:

```
I need input for [N] fields before continuing:

[1] "Why are you interested in this role?" (open text)
    No previous answer found.

[2] "Years of experience in software development" (select)
    Options: Less than 1 | 1-3 | 3-5 | 5-10 | 10+
    Suggested: 5-10 (from your experience history since 2020-06)

[3] "Expected salary" (text — always_prompt)
    Suggested: 175000 (from your profile)
    Note: This field always requires your confirmation.
```

The user can reply: `"1: I'm passionate about this. 2: 5-10. 3: 180000"`

"accept" uses the suggestion. "skip" leaves blank (use with caution on required fields).

Wait for user reply before filling these fields.

**EEO fields (gender, race, veteran, disability)** have `autofill` policy — fill them automatically from
the profile without prompting. If the profile has no EEO value and the resolver returns `ask_user`,
ask the user once, then **persist to profile** so it autofills on future applications:

```bash
uv run autoapply profile set eeo.gender "Male"
uv run autoapply profile set eeo.race_ethnicity "Asian"
uv run autoapply profile set eeo.veteran_status "I am not a protected veteran"
uv run autoapply profile set eeo.disability_status "I don't wish to answer"
```

### 3H: Fill user-provided answers in batch

Use the same recipe-driven approach as 3D — check `interaction_recipe` for each user-answered field and apply the appropriate pattern:

```bash
uvx browser-use python "
import time
# User-provided text answers
user_fields = [
    (22, '5-10'),    # years of experience — user selected
    (31, '180000'),  # expected salary — user provided
]
for idx, val in user_fields:
    browser.input(idx, val)
    time.sleep(0.1)

# User-confirmed selects / combos — use recipe pattern if available
user_combos = [
    (28, 'Female'),  # gender — user confirmed; recipe says combobox → click/type/Enter
]
for idx, val in user_combos:
    browser.click(idx)
    time.sleep(0.3)
    browser.type(val)
    time.sleep(0.4)
    browser.keys('Enter')
"
```

### 3I: Validate, screenshot, and navigate

**Pre-navigation check** — run before every Save/Continue click to prevent validation error round-trips:

```bash
uvx browser-use state
```

Scan the output for:
- Any `Error` text (inline field errors)
- `required=true` inputs with placeholder/empty values: `MM`, `YYYY`, `MM/YYYY`, `Select One`, `""`
- Date segment displays still showing `MM` or `YYYY` (not filled yet)

If issues found, fix them using the appropriate recipe, then re-scan. For date segments verify with eval:

```bash
uvx browser-use eval "document.getElementById('<dateSectionMonth-display-id>').textContent"
```

Once state is clean, take screenshot and click:

```bash
uvx browser-use screenshot
uvx browser-use click <next_or_save_button_index>
```

Wait 1-2 seconds, then run `uvx browser-use state` again:
- **`Errors Found` still visible** → navigation failed; fix remaining errors and retry
- **New page/step appears** → proceed to Step 3A for the new page

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

Wait for confirmation page. Take a screenshot to confirm success:

```bash
uvx browser-use screenshot
```

---

## Step 6: Record the Application

When building `qa_pairs`, **include `interaction_recipe`** for any field that used a non-standard interaction (combobox, date_segmented, react_virtualized). Use `{idx}` and `{answer}` as placeholders — not hardcoded values — so the recipe works on the next application too.

```bash
uv run autoapply history add '{
  "id": "<uuid4>",
  "url": "<job_url>",
  "company": "<company>",
  "job_title": "<title>",
  "applied_at": "<ISO8601>",
  "status": "submitted",
  "qa_pairs": [
    {
      "field_label": "State",
      "field_type": "combobox",
      "answer": "Illinois",
      "source": "profile",
      "user_verified": false,
      "interaction_recipe": {
        "widget_type": "combobox",
        "ats_platform": "workday",
        "description": "Click to open, type to filter, Enter to select",
        "steps": [
          {"action": "click", "target": "{idx}", "wait_ms": 300},
          {"action": "type", "target": "{idx}", "value": "{answer}", "wait_ms": 500},
          {"action": "keys", "target": "Enter", "wait_ms": 300}
        ]
      }
    },
    {
      "field_label": "First Name",
      "field_type": "text",
      "answer": "Xinyu",
      "source": "profile",
      "user_verified": false,
      "interaction_recipe": null
    }
  ]
}'
```

For **standard text fields** (First Name, Email, etc.), `interaction_recipe` should be `null` — no recipe needed.

Generate UUID and timestamp:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())"
```

---

## Operational Tips

- **Always invoke browser-use as `uvx browser-use`** (it's a Python tool, not npm). Never use `browser-use` or `npx browser-use`.
- **Always use `--headed`** so the user can see the browser in real time.
- **Batch is the default** — only fall back to individual commands for tricky fields that fail.
- **Use `interaction_recipe` first** — if the resolver returns a recipe, follow it exactly. Never trial-and-error for combo-boxes, date fields, or ReactVirtualized dropdowns.
- **Workday shadow DOM**: Inputs are often inside shadow roots. If `uvx browser-use input <idx>` fails,
  use `uvx browser-use eval "document.querySelector('...').value = '...'"` or click by pixel coordinates.
- **Combobox vs select**: In Workday, most dropdowns are comboboxes (`role="combobox"`), not native `<select>`. They need click → type → Enter, not click → select. Identify them in Step 3A.
- **CAPTCHA**: Tell user "A CAPTCHA appeared — please solve it, then let me know to continue."
- **Page reload**: `uvx browser-use eval "window.location.reload()"`
- **Scroll to reveal hidden fields**: `uvx browser-use scroll down`
- **If batch fill partially fails**: The python script prints ERR lines — fix only those fields
  individually, don't re-run the whole batch.
- **File uploads**: `uvx browser-use upload <index> "<absolute_path>"`
  Get path from: `uv run autoapply profile show documents`

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
