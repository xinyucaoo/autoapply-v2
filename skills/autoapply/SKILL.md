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
browser-use --headed open "<url>"
```

Get state (not screenshot) to find the Apply button:

```bash
browser-use state
```

Click Apply and navigate to the application form:

```bash
browser-use click <index>
```

---

## Step 3: Per-Page Batch Workflow

Repeat this workflow for **each page** of the application form.

### 3A: Scan the page

```bash
browser-use state
```

From the state output, identify ALL form fields on the current page:
- Their element indices
- Their labels / aria-labels
- Their types (text, select/dropdown, radio, checkbox, textarea, file)
- Available options for selects/radios

### 3B: Batch resolve ALL fields at once

Build a single JSON array of all fields and call the resolver once:

```bash
autoapply resolve-batch --company "<company>" --fields '[
  {"label": "First Name", "type": "text"},
  {"label": "Email", "type": "text"},
  {"label": "Work Authorization", "type": "select", "options": ["Yes", "No"]},
  {"label": "Gender", "type": "select", "options": ["Male", "Female", "Decline to State"]}
]'
```

This returns a JSON array — one result per field — loaded in a single subprocess call.

### 3C: Classify fields by policy

Split the resolved fields into two groups:

**AUTOFILL** (policy=`autofill`, confidence=`high`) — fill without asking:
- text, textarea, file fields: use `browser-use python` to fill in batch
- select/radio/checkbox fields: use `browser-use python` to click/select in batch

**PROMPT** (policy=`suggest_only`, `always_prompt`, or `ask_user`) — collect and ask user.

### 3D: Batch fill autofill text fields

Fill all autofill text/textarea inputs in a single `browser-use python` call:

```bash
browser-use python "
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

### 3E: Batch fill autofill selects/dropdowns

Fill all autofill select/dropdown/radio fields in one call:

```bash
browser-use python "
import time
results = []

# Dropdowns: click to open, then select
dropdowns = [
    (12, 'Yes'),    # Work Authorization
    (15, 'No'),     # Sponsorship
]
for idx, option in dropdowns:
    try:
        browser.click(idx)
        time.sleep(0.3)
        browser.select(idx, option)
        results.append(f'OK: [{idx}]={option!r}')
    except Exception as e:
        results.append(f'ERR: [{idx}] {e}')

print('\n'.join(results))
"
```

For **Workday-style dropdowns** (combo boxes): click to open, type to filter, then press Enter:
```bash
browser-use python "
import time
browser.click(42)   # open combo box
time.sleep(0.3)
browser.type('Computer Engineering')
time.sleep(0.3)
browser.keys('Enter')
time.sleep(0.5)
# options now filtered — find and click the match
"
```

For **radio buttons / checkboxes**: click by index or use JS:
```bash
browser-use eval "document.querySelector('[aria-label=\"Yes\"]').click()"
```

### 3F: Take a single verification screenshot

After batch filling autofill fields:

```bash
browser-use screenshot
```

Visually confirm the filled values look correct. If anything is wrong, fix it before proceeding.

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

[3] "Gender" (select — suggest_only)
    Options: Male | Female | Non-binary | Prefer not to say
    Suggested: Female (from your profile)

[4] "Expected salary" (text — always_prompt)
    Suggested: 175000 (from your profile)
    Note: This field always requires your confirmation.
```

The user can reply: `"1: I'm passionate about this. 2: 5-10. 3: accept. 4: 180000"`

"accept" uses the suggestion. "skip" leaves blank (use with caution on required fields).

Wait for user reply before filling these fields.

### 3H: Fill user-provided answers in batch

```bash
browser-use python "
import time
# User-provided answers
user_fields = [
    (22, '5-10'),    # years of experience — user selected
    (31, '180000'),  # expected salary — user provided
]
for idx, val in user_fields:
    browser.input(idx, val)
    time.sleep(0.1)

# User-confirmed selects
user_selects = [
    (28, 'Female'),  # gender — user confirmed
]
for idx, option in user_selects:
    browser.click(idx)
    time.sleep(0.3)
    browser.select(idx, option)
"
```

### 3I: Navigate to next page

```bash
browser-use state
browser-use click <next_or_save_button_index>
```

Wait 1-2 seconds for page transition, then repeat from Step 3A.

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
browser-use click <submit_button_index>
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
