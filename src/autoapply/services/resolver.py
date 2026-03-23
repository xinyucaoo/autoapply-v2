"""
Field resolver: deterministic mapping from form field labels to profile values.

Resolution order:
1. Canonical mapping (exact normalized label -> profile path)
2. Alias mapping (known synonyms)
3. Scoped history match
4. Return null (Claude Code falls back to NLU or asks user)
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Any

from autoapply.models.profile import Profile
from autoapply.models.history import ApplicationHistory
from autoapply.services.history_store import lookup_answer

# Default answer policies per profile path prefix
DEFAULT_POLICIES: dict[str, str] = {
    "personal": "autofill",
    "work_authorization": "autofill",
    "education": "autofill",
    "experience": "autofill",
    "skills": "autofill",
    "certifications": "autofill",
    "documents": "autofill",
    "preferences.remote_preference": "autofill",
    "preferences.years_of_experience": "autofill",
    "eeo": "autofill",
    "cover_letter": "suggest_only",
    "preferences.relocation_willing": "suggest_only",
    "preferences.desired_start_date": "always_prompt",
    "salary": "always_prompt",
}

# Canonical field map: normalized label -> profile_path
# Policy comes from DEFAULT_POLICIES unless overridden in profile.
CANONICAL_MAP: dict[str, str] = {
    # Personal — name
    "first name": "personal.first_name",
    "first": "personal.first_name",
    "given name": "personal.first_name",
    "legal first name": "personal.first_name",
    "legal given name": "personal.first_name",
    "nombre": "personal.first_name",
    "last name": "personal.last_name",
    "last": "personal.last_name",
    "surname": "personal.last_name",
    "family name": "personal.last_name",
    "apellido": "personal.last_name",
    "full name": "__computed__.full_name",
    "name": "__computed__.full_name",
    "full legal name": "__computed__.full_name",
    "your name": "__computed__.full_name",
    "preferred name": "personal.preferred_name",
    "preferred first name": "personal.preferred_name",
    "pronouns": "personal.pronouns",
    "preferred pronouns": "personal.pronouns",
    # Personal — contact
    "email": "personal.email",
    "email address": "personal.email",
    "e-mail": "personal.email",
    "e-mail address": "personal.email",
    "work email": "personal.email",
    "personal email": "personal.email",
    "phone": "personal.phone",
    "phone number": "personal.phone",
    "mobile": "personal.phone",
    "mobile number": "personal.phone",
    "mobile phone": "personal.phone",
    "telephone": "personal.phone",
    "telephone number": "personal.phone",
    "cell": "personal.phone",
    "cell phone": "personal.phone",
    "contact number": "personal.phone",
    # Personal — address
    "street address": "personal.address.street",
    "address line 1": "personal.address.street",
    "address": "personal.address.street",
    "street": "personal.address.street",
    "city": "personal.address.city",
    "town": "personal.address.city",
    "state": "personal.address.state",
    "state province": "personal.address.state",
    "province": "personal.address.state",
    "state or province": "personal.address.state",
    "zip": "personal.address.zip",
    "zip code": "personal.address.zip",
    "postal code": "personal.address.zip",
    "postcode": "personal.address.zip",
    "country": "personal.address.country",
    "country of residence": "personal.address.country",
    # Personal — online presence
    "linkedin": "personal.linkedin_url",
    "linkedin url": "personal.linkedin_url",
    "linkedin profile": "personal.linkedin_url",
    "linkedin profile url": "personal.linkedin_url",
    "linkedin profile link": "personal.linkedin_url",
    "website": "personal.portfolio_url",
    "portfolio": "personal.portfolio_url",
    "portfolio url": "personal.portfolio_url",
    "personal website": "personal.portfolio_url",
    "personal site": "personal.portfolio_url",
    "portfolio website": "personal.portfolio_url",
    "github": "personal.github_url",
    "github url": "personal.github_url",
    "github profile": "personal.github_url",
    "github profile url": "personal.github_url",
    # Work authorization
    "authorized to work": "work_authorization.authorized_us",
    "legally authorized": "work_authorization.authorized_us",
    "work authorization": "work_authorization.authorized_us",
    "authorized to work in the us": "work_authorization.authorized_us",
    "authorized to work in the united states": "work_authorization.authorized_us",
    "are you authorized to work in the us": "work_authorization.authorized_us",
    "are you legally authorized to work in the united states": "work_authorization.authorized_us",
    "us work authorization": "work_authorization.authorized_us",
    "sponsorship": "work_authorization.sponsorship_needed",
    "visa sponsorship": "work_authorization.sponsorship_needed",
    "require sponsorship": "work_authorization.sponsorship_needed",
    "require visa sponsorship": "work_authorization.sponsorship_needed",
    "will you now or in the future require sponsorship": "work_authorization.sponsorship_needed",
    "do you require visa sponsorship": "work_authorization.sponsorship_needed",
    "need sponsorship": "work_authorization.sponsorship_needed",
    "citizenship": "work_authorization.citizenship",
    "citizenship status": "work_authorization.citizenship",
    "country of citizenship": "work_authorization.citizenship",
    "visa status": "work_authorization.visa_status",
    "current visa status": "work_authorization.visa_status",
    # Education
    "school": "education.0.school",
    "university": "education.0.school",
    "college": "education.0.school",
    "institution": "education.0.school",
    "school name": "education.0.school",
    "school or university": "education.0.school",
    "university name": "education.0.school",
    "degree": "education.0.degree",
    "degree type": "education.0.degree",
    "highest degree": "education.0.degree",
    "highest level of education": "education.0.degree",
    "field of study": "education.0.field",
    "major": "education.0.field",
    "area of study": "education.0.field",
    "concentration": "education.0.field",
    "graduation date": "education.0.graduation_date",
    "graduation year": "education.0.graduation_date",
    "year of graduation": "education.0.graduation_date",
    "expected graduation": "education.0.graduation_date",
    "gpa": "education.0.gpa",
    "grade point average": "education.0.gpa",
    "overall result": "education.0.gpa",
    "overall result (gpa)": "education.0.gpa",
    # Experience — company
    "current company": "experience.0.company",
    "current employer": "experience.0.company",
    "most recent employer": "experience.0.company",
    "employer": "experience.0.company",
    "employer name": "experience.0.company",
    "company": "experience.0.company",
    "company name": "experience.0.company",
    "organization": "experience.0.company",
    "organization name": "experience.0.company",
    "name of employer": "experience.0.company",
    "name of company": "experience.0.company",
    "place of employment": "experience.0.company",
    # Experience — title
    "current title": "experience.0.title",
    "current position": "experience.0.title",
    "job title": "experience.0.title",
    "position": "experience.0.title",
    "position title": "experience.0.title",
    "title": "experience.0.title",
    "role": "experience.0.title",
    "job role": "experience.0.title",
    "occupation": "experience.0.title",
    # Experience — dates (unambiguous labels only; "start date"/"end date" are too ambiguous)
    "from date": "experience.0.start_date",
    "employment start date": "experience.0.start_date",
    "to date": "experience.0.end_date",
    "employment end date": "experience.0.end_date",
    # Experience — location
    "work location": "experience.0.location",
    "job location": "experience.0.location",
    "location": "experience.0.location",
    # Experience — description
    "description": "experience.0.description",
    "job description": "experience.0.description",
    "responsibilities": "experience.0.description",
    "duties": "experience.0.description",
    "describe your role": "experience.0.description",
    "describe your responsibilities": "experience.0.description",
    # EEO / demographics
    "gender": "eeo.gender",
    "gender identity": "eeo.gender",
    "what is your gender?": "eeo.gender",
    "what is your gender": "eeo.gender",
    "sex": "eeo.gender",
    "race": "eeo.race_ethnicity",
    "ethnicity": "eeo.race_ethnicity",
    "race ethnicity": "eeo.race_ethnicity",
    "race or ethnicity": "eeo.race_ethnicity",
    "hispanic": "eeo.race_ethnicity",
    "hispanic or latino": "eeo.race_ethnicity",
    "are you hispanic or latino": "eeo.race_ethnicity",
    "veteran status": "eeo.veteran_status",
    "veteran": "eeo.veteran_status",
    "are you a veteran": "eeo.veteran_status",
    "protected veteran status": "eeo.veteran_status",
    "disability": "eeo.disability_status",
    "disability status": "eeo.disability_status",
    "do you have a disability": "eeo.disability_status",
    # Preferences / salary
    "salary": "salary.desired",
    "expected salary": "salary.desired",
    "desired salary": "salary.desired",
    "salary expectation": "salary.desired",
    "salary expectations": "salary.desired",
    "salary range": "salary.desired",
    "desired compensation": "salary.desired",
    "compensation expectations": "salary.desired",
    "annual salary": "salary.desired",
    "minimum salary": "salary.minimum",
    "start date": "preferences.desired_start_date",
    "desired start date": "preferences.desired_start_date",
    "available start date": "preferences.desired_start_date",
    "when can you start": "preferences.desired_start_date",
    "earliest start date": "preferences.desired_start_date",
    "remote": "preferences.remote_preference",
    "work arrangement": "preferences.remote_preference",
    "remote preference": "preferences.remote_preference",
    "work location preference": "preferences.remote_preference",
    "work style": "preferences.remote_preference",
    "relocation": "preferences.relocation_willing",
    "willing to relocate": "preferences.relocation_willing",
    "open to relocation": "preferences.relocation_willing",
    "are you willing to relocate": "preferences.relocation_willing",
    "years of experience": "preferences.years_of_experience",
    "years experience": "preferences.years_of_experience",
    "how many years of experience": "preferences.years_of_experience",
    "total years of experience": "preferences.years_of_experience",
}


def _normalize(label: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    label = label.lower()
    label = re.sub(r"[^\w\s]", " ", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def _get_profile_value(profile: Profile, path: str) -> Any:
    """Get a value from profile by dot-path. Returns None if not found."""
    if path.startswith("__computed__"):
        key = path.split(".")[-1]
        if key == "full_name":
            parts = [profile.personal.first_name, profile.personal.last_name]
            value = " ".join(p for p in parts if p)
            return value or None
        return None

    parts = path.split(".")
    obj: Any = profile.model_dump()
    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return obj


def _get_policy(path: str, profile: Profile) -> str:
    """Determine the fill policy for a profile path."""
    # User overrides take priority
    overrides = profile.answer_policies or {}
    for pattern, policy in overrides.items():
        pattern_norm = pattern.rstrip(".*")
        if path.startswith(pattern_norm):
            return policy

    # Default policies — check more specific prefixes first
    # Sort by length descending so longer (more specific) prefixes match first
    sorted_defaults = sorted(DEFAULT_POLICIES.items(), key=lambda x: len(x[0]), reverse=True)
    for prefix, policy in sorted_defaults:
        if path == prefix or path.startswith(prefix + "."):
            return policy

    return "autofill"


@dataclass
class ResolveResult:
    answer: Any | None
    source: str | None      # "profile", "history", "custom_qa", None
    profile_path: str | None
    confidence: str | None  # "high", "medium", None
    policy: str             # "autofill", "suggest_only", "always_prompt", "never_store"
    suggestion: str | None  # Human-readable suggestion text
    interaction_recipe: dict | None = None  # Serialized InteractionRecipe, if known


def resolve_batch(
    fields: list[dict],
    company: str | None = None,
    profile: Profile | None = None,
    history: ApplicationHistory | None = None,
    ats_platform: str | None = None,
) -> list[dict]:
    """
    Resolve multiple form fields in a single call.

    Loads profile and history once (if not provided), then resolves each field.

    Args:
        fields: list of dicts with keys: label (str), type (str, optional),
                options (list[str], optional)
        company: company name for scoped history lookup
        profile: pre-loaded Profile (skips disk load; useful in tests)
        history: pre-loaded ApplicationHistory (skips disk load; useful in tests)
        ats_platform: ATS identifier ("workday", "greenhouse", etc.) for playbook lookup

    Returns:
        list of dicts with keys: label, answer, source, profile_path,
        confidence, policy, suggestion, interaction_recipe
    """
    from autoapply.services.profile_store import load_profile
    from autoapply.services.history_store import load_history

    if profile is None:
        profile = load_profile()
    if history is None:
        history = load_history()

    results = []
    for field in fields:
        label = field.get("label", "")
        field_type = field.get("type", "text")
        options = field.get("options")
        result = resolve(
            label=label,
            field_type=field_type,
            options=options,
            company=company,
            profile=profile,
            history=history,
            ats_platform=ats_platform,
        )
        results.append({
            "label": label,
            "answer": result.answer,
            "source": result.source,
            "profile_path": result.profile_path,
            "confidence": result.confidence,
            "policy": result.policy,
            "suggestion": result.suggestion,
            "interaction_recipe": result.interaction_recipe,
        })
    return results


def resolve(
    label: str,
    field_type: str = "text",
    options: list[str] | None = None,
    company: str | None = None,
    profile: Profile | None = None,
    history: ApplicationHistory | None = None,
    ats_platform: str | None = None,
) -> ResolveResult:
    """
    Resolve a form field label to an answer.

    Returns a ResolveResult with answer, source, confidence, and policy.
    """
    from autoapply.services.profile_store import load_profile
    from autoapply.services.history_store import load_history

    if profile is None:
        profile = load_profile()
    if history is None:
        history = load_history()

    from autoapply.services.playbooks import lookup_playbook

    normalized = _normalize(label)

    def _recipe(qa_pair=None) -> dict | None:
        """Return a serialized recipe: prefer stored history recipe, fall back to playbook."""
        if qa_pair is not None and qa_pair.interaction_recipe is not None:
            return qa_pair.interaction_recipe.model_dump()
        playbook = lookup_playbook(ats_platform, field_type)
        return playbook.model_dump() if playbook else None

    # Step 1 & 2: Canonical + alias mapping
    profile_path = CANONICAL_MAP.get(normalized)
    if profile_path:
        value = _get_profile_value(profile, profile_path)
        policy = _get_policy(profile_path, profile)
        if value is not None:
            # For boolean values, convert to human-readable
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            else:
                value = str(value) if not isinstance(value, str) else value

            suggestion = f"{value} (from profile: {profile_path})"
            return ResolveResult(
                answer=value,
                source="profile",
                profile_path=profile_path,
                confidence="high",
                policy=policy,
                suggestion=suggestion if policy != "autofill" else None,
                interaction_recipe=_recipe(),
            )

    # Step 3: Custom Q&A in profile
    for qa in profile.custom_qa:
        if _normalize(qa.question) in normalized or normalized in _normalize(qa.question):
            policy = qa.policy or "autofill"
            return ResolveResult(
                answer=qa.answer,
                source="custom_qa",
                profile_path=None,
                confidence="high",
                policy=policy,
                suggestion=f"{qa.answer} (from custom Q&A)",
                interaction_recipe=_recipe(),
            )

    # Step 4: History lookup
    qa_match = lookup_answer(history, label, company=company)
    if qa_match:
        return ResolveResult(
            answer=qa_match.answer,
            source="history",
            profile_path=qa_match.normalized_key,
            confidence="medium",
            policy="suggest_only",  # History matches are always suggestions
            suggestion=f"{qa_match.answer} (from previous application)",
            interaction_recipe=_recipe(qa_match),
        )

    # No match
    return ResolveResult(
        answer=None,
        source=None,
        profile_path=profile_path,
        confidence=None,
        policy="ask_user",
        suggestion=None,
        interaction_recipe=_recipe(),
    )
