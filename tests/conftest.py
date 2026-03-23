import os
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def tmp_autoapply_dir(tmp_path, monkeypatch):
    """Redirect ~/.autoapply to a tmp directory for all tests."""
    monkeypatch.setenv("AUTOAPPLY_DIR", str(tmp_path / ".autoapply"))
    # Also patch the config module's constants
    import autoapply.config as cfg
    cfg.AUTOAPPLY_DIR = tmp_path / ".autoapply"
    cfg.PROFILE_FILE = cfg.AUTOAPPLY_DIR / "profile.json"
    cfg.HISTORY_FILE = cfg.AUTOAPPLY_DIR / "history.json"
    # Patch the service modules that import from config at module load time
    import autoapply.services.profile_store as ps
    ps.AUTOAPPLY_DIR = cfg.AUTOAPPLY_DIR
    ps.PROFILE_FILE = cfg.PROFILE_FILE
    import autoapply.services.history_store as hs
    hs.AUTOAPPLY_DIR = cfg.AUTOAPPLY_DIR
    hs.HISTORY_FILE = cfg.HISTORY_FILE


@pytest.fixture
def sample_profile():
    """Return a Profile with realistic data for tests."""
    from autoapply.models.profile import (
        Profile, Personal, Address, WorkAuthorization,
        Education, Experience, EEO, Salary, Preferences, CustomQA
    )
    return Profile(
        personal=Personal(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="555-123-4567",
            address=Address(
                street="123 Main St",
                city="San Francisco",
                state="CA",
                zip="94102",
                country="United States",
            ),
            linkedin_url="https://linkedin.com/in/janedoe",
            github_url="https://github.com/janedoe",
            portfolio_url="https://janedoe.dev",
        ),
        work_authorization=WorkAuthorization(
            authorized_us=True,
            sponsorship_needed=False,
            citizenship="US Citizen",
        ),
        education=[
            Education(
                school="MIT",
                degree="Bachelor of Science",
                field="Computer Science",
                graduation_date="2020-05",
                gpa="3.8",
            )
        ],
        experience=[
            Experience(
                company="Acme Corp",
                title="Software Engineer",
                start_date="2020-06",
                description="Built distributed systems.",
            )
        ],
        eeo=EEO(
            gender="Female",
            race_ethnicity="Asian",
            veteran_status="Not a veteran",
            disability_status="No disability",
        ),
        salary=Salary(minimum=150000, desired=175000),
        preferences=Preferences(
            remote_preference="remote",
            relocation_willing=False,
            desired_start_date="2026-05-01",
            years_of_experience=5,
        ),
        custom_qa=[
            CustomQA(
                question="why are you interested",
                answer="I am passionate about building scalable systems.",
                policy="autofill",
            )
        ],
    )


@pytest.fixture
def sample_history():
    """Return an ApplicationHistory with some Q&A pairs for tests."""
    from autoapply.models.history import ApplicationHistory, ApplicationRecord, QAPair
    return ApplicationHistory(
        applications=[
            ApplicationRecord(
                id="aaaaaaaa-0000-0000-0000-000000000001",
                url="https://acme.com/jobs/123",
                company="Acme Corp",
                job_title="Senior Engineer",
                applied_at="2026-01-15T10:00:00+00:00",
                status="submitted",
                qa_pairs=[
                    QAPair(
                        field_label="How did you hear about us?",
                        field_type="select",
                        answer="LinkedIn",
                        source="user",
                        company="Acme Corp",
                        user_verified=True,
                    ),
                    QAPair(
                        field_label="Cover letter",
                        field_type="textarea",
                        answer="I am excited to apply...",
                        source="user",
                        company="Acme Corp",
                        user_verified=False,
                    ),
                ],
            ),
            ApplicationRecord(
                id="bbbbbbbb-0000-0000-0000-000000000002",
                url="https://beta.com/jobs/456",
                company="Beta Inc",
                job_title="Staff Engineer",
                applied_at="2026-02-10T12:00:00+00:00",
                status="in_progress",
                qa_pairs=[
                    QAPair(
                        field_label="How did you hear about us?",
                        field_type="select",
                        answer="Referral",
                        source="user",
                        company="Beta Inc",
                        user_verified=True,
                    ),
                ],
            ),
        ]
    )
