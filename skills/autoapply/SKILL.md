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

---

## Step 1: Prerequisites Check

Load the user's profile and confirm it exists:

```bash
autoapply profile show
```

If the output is an empty profile (all blank fields) or the command fails, stop and tell the user:

> "No profile found. Run `autoapply profile init` and fill in your details before applying."

---

## Step 2: Load Context

Load relevant history for this company to inform later resolution:

```bash
autoapply profile show
autoapply history search "<company name>"
```

Note the company name and job title from the URL or user's request — you'll need them throughout.

---

## Step 3: Open the Job Page

```bash
browser-use --headed open "<url>"
```

Take a screenshot and look for an "Apply", "Apply Now", or "Easy Apply" button. Click it:

```bash
browser-use click <index>
```

If the application opens in a new tab or iframe, navigate to it.

---

## Step 4: Scan Form Fields

Get the current page state to see all form elements:

```bash
browser-use state
```

This returns a numbered list of interactive elements. Identify all form fields:
- Text inputs (type=text, email, tel, url, number)
- Textareas
- Select dropdowns
- Radio button groups
- Checkboxes
- File upload inputs

For each select/radio/checkbox, note the available options.

---

## Step 5: Per-Field Resolution Loop

For EACH form field on the current page, call the resolver before deciding what to fill:

```bash
autoapply resolve "<field label>" --type <type> --company "<company>" [--options "opt1,opt2,opt3"]
```

Examples:
```bash
autoapply resolve "First Name" --type text --company "Acme Corp"
autoapply resolve "Work Authorization" --type select --options "US Citizen,Green Card,H-1B,Other" --company "Acme Corp"
autoapply resolve "Desired Salary" --type text --company "Acme Corp"
autoapply resolve "Gender" --type select --options "Male,Female,Non-binary,Prefer not to say,Decline to state" --company "Acme Corp"
```

The resolver outputs JSON:
```json
{
  "answer": "Jane",
  "source": "profile",
  "profile_path": "personal.first_name",
  "confidence": "high",
  "policy": "autofill",
  "suggestion": null
}
```

---

## Step 6: Policy Enforcement

Apply the following rules based on the `policy` field:

### `autofill` + `confidence: high`
Fill the field immediately without asking the user.

```bash
browser-use input <index> "Jane"
```

### `suggest_only`
Do NOT fill yet. Collect this field for the batch prompt (Step 7).

### `always_prompt`
Do NOT fill yet. Always collect for batch prompt even if an answer is available.

### `ask_user` (answer is null)
Do NOT fill yet. Collect for batch prompt. Claude Code may infer from profile context
as a suggested answer, but must present it to the user for confirmation.

---

## Step 7: Batched User Prompts

After processing all fields on the current page section, collect all fields that need
user input (suggest_only, always_prompt, ask_user) and present them TOGETHER in a
single numbered list before filling any of them.

Format:

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

[5] "How did you hear about us?" (select)
    Options: LinkedIn | Referral | Company website | Job board | Other
    Previous answer at Acme Corp: LinkedIn
```

The user can reply with just the answers:
> "1: I'm passionate about distributed systems. 2: 5-10. 3: accept. 4: 180000. 5: LinkedIn"

Or "accept" / "skip" any suggestion. "skip" leaves the field blank (use with caution).

Wait for the user's reply before proceeding to fill any of these fields.

---

## Step 8: Fill Fields

After collecting all answers (from autofill + user responses), fill them one by one:

**Text/textarea:**
```bash
browser-use input <index> "<answer>"
```

**Select dropdown:**
```bash
browser-use click <index>   # Open dropdown
browser-use state            # Read options
browser-use select <index> "<option value>"
```

**Radio button:**
```bash
browser-use state            # Read all radio options
browser-use click <radio_index>  # Click the matching option
```

**Checkbox (yes/no):**
```bash
browser-use click <index>    # Toggle on if answer is "Yes"/"true"
```

**File upload (resume/cover letter):**
```bash
# Get document path from profile
autoapply profile show documents
browser-use upload <index> "<absolute_path_to_file>"
```

After filling each field, verify it was accepted:
```bash
browser-use get value <index>
```

---

## Step 9: Multi-Page Navigation

Look for "Next", "Continue", "Save and Continue", or "Next Step" buttons:

```bash
browser-use state            # Find navigation buttons
browser-use click <next_button_index>
```

After clicking, wait for the page to update, then repeat Steps 4-8 for the new page.
Track which pages you've completed and which fields you've filled.

---

## Step 10: Pre-Submission Review

Before clicking Submit, compile a summary table of ALL fields filled across all pages
and present it to the user:

```
Ready to submit your application to Acme Corp — Senior Engineer.

Here is a summary of all fields filled:

PERSONAL
  First Name:           Jane
  Last Name:            Doe
  Email:                jane@example.com
  Phone:                555-123-4567
  LinkedIn:             https://linkedin.com/in/janedoe

WORK AUTHORIZATION
  Authorized (US):      Yes
  Sponsorship needed:   No

EDUCATION
  School:               MIT
  Degree:               Bachelor of Science
  Field:                Computer Science
  Graduation:           2020-05

CUSTOM / MANUAL
  Why interested:       I'm passionate about distributed systems.
  Expected salary:      180000
  Gender:               Female (you confirmed)

Shall I submit? (yes / no / edit <field>)
```

Wait for the user to confirm "yes" before proceeding.

---

## Step 11: Submit

```bash
browser-use click <submit_button_index>
```

Wait for the confirmation page or success message. Take a screenshot to confirm.
If you see an error, report it to the user before recording.

---

## Step 12: Record the Application

Build and save the ApplicationRecord with all Q&A pairs:

```bash
autoapply history add '{
  "id": "<uuid4>",
  "url": "<job_url>",
  "company": "<company>",
  "job_title": "<title>",
  "applied_at": "<ISO8601_timestamp>",
  "status": "submitted",
  "qa_pairs": [
    {
      "field_label": "First Name",
      "normalized_key": "personal.first_name",
      "field_type": "text",
      "answer": "Jane",
      "source": "profile",
      "company": "<company>",
      "user_verified": false
    },
    {
      "field_label": "Expected salary",
      "normalized_key": "salary.desired",
      "field_type": "text",
      "answer": "180000",
      "source": "user",
      "company": "<company>",
      "user_verified": true
    }
  ]
}'
```

Rules for `source` and `user_verified`:
- `source: "profile"` — answer came from autoapply resolver, policy was autofill
- `source: "user"` — user typed a new answer or corrected a suggestion
- `source: "history"` — answer came from a previous application
- `source: "inference"` — you inferred the answer from profile context
- `user_verified: true` — user explicitly confirmed or typed the answer
- `user_verified: false` — autofilled without user interaction

Generate a UUID4 with:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

Get the current timestamp with:
```bash
python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())"
```

---

## Field Mapping Reference

When the resolver returns `answer: null` and you need to infer from profile context,
use this table as a guide. Always present inferred answers as suggestions, never autofill.

| Form Field Pattern | Profile Path | Notes |
|---|---|---|
| first name, given name, legal first name | personal.first_name | |
| last name, surname, family name | personal.last_name | |
| full name, legal name | personal.first_name + " " + personal.last_name | Combine |
| preferred name, nickname | personal.preferred_name | |
| pronouns | personal.pronouns | |
| email, e-mail, work email | personal.email | |
| phone, mobile, cell, telephone | personal.phone | |
| street address, address line 1 | personal.address.street | |
| city, town | personal.address.city | |
| state, province | personal.address.state | |
| zip, postal code | personal.address.zip | |
| country | personal.address.country | |
| linkedin, linkedin url | personal.linkedin_url | |
| github, github url | personal.github_url | |
| website, portfolio | personal.portfolio_url | |
| authorized to work in US | work_authorization.authorized_us | Yes/No |
| require sponsorship | work_authorization.sponsorship_needed | Yes/No (invert: "No" is good) |
| citizenship, citizenship status | work_authorization.citizenship | |
| visa status | work_authorization.visa_status | |
| school, university, college | education.0.school | Most recent |
| degree, degree type | education.0.degree | |
| field of study, major | education.0.field | |
| graduation date, year | education.0.graduation_date | YYYY-MM |
| GPA | education.0.gpa | |
| current company, employer | experience.0.company | Most recent |
| current title, job title, position | experience.0.title | |
| gender, gender identity, sex | eeo.gender | suggest_only |
| race, ethnicity | eeo.race_ethnicity | suggest_only |
| veteran status | eeo.veteran_status | suggest_only |
| disability status | eeo.disability_status | suggest_only |
| salary, expected salary, desired comp | salary.desired | always_prompt |
| minimum salary | salary.minimum | always_prompt |
| start date, when can you start | preferences.desired_start_date | always_prompt |
| remote preference, work arrangement | preferences.remote_preference | |
| willing to relocate | preferences.relocation_willing | suggest_only |
| years of experience | preferences.years_of_experience | |

---

## Operational Tips

- Always use `browser-use --headed` so the user can see what's happening in real time.
- After filling each field with `browser-use input`, verify with `browser-use get value <index>`.
- For dropdowns: open with click, then read state to see actual option values before selecting.
- For radio groups: read all options from state before deciding which to click.
- For file uploads: use `browser-use upload <index> <absolute_path>` with the path from `autoapply profile show documents`.
- If a CAPTCHA appears: tell the user "A CAPTCHA appeared — please solve it in the browser, then let me know when to continue."
- If the page fails to load or goes blank:
  ```bash
  browser-use eval "window.location.reload()"
  ```
- Scroll down periodically to reveal hidden form sections:
  ```bash
  browser-use scroll down
  ```
- If a required field is missed before submission, the page will usually highlight it — take a screenshot, identify the field, resolve it, fill it, and retry submit.
- For optional fields the user wants to skip: confirm with the user before leaving them blank.
- If the job application redirects to a third-party ATS (Greenhouse, Lever, Workday, etc.), continue the workflow on that page — the resolver works the same regardless of ATS.
- For multi-step forms, track your progress by noting which page/step number you're on.
- If an application cannot be completed (login wall, broken form, etc.), record it with `status: "failed"` and explain to the user.
