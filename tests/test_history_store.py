import pytest
from autoapply.models.history import ApplicationHistory, ApplicationRecord, QAPair
from autoapply.services.history_store import (
    load_history, save_history, add_record, new_record,
    search_qa, lookup_answer
)


def test_load_history_returns_empty_when_no_file():
    """load_history() returns empty ApplicationHistory when no file exists."""
    h = load_history()
    assert isinstance(h, ApplicationHistory)
    assert h.applications == []


def test_add_record_and_roundtrip():
    """add_record() + save_history() + load_history() persists the record."""
    h = load_history()
    record = new_record(
        url="https://example.com/jobs/1",
        company="Example Co",
        job_title="Engineer",
    )
    h = add_record(h, record)
    save_history(h)

    loaded = load_history()
    assert len(loaded.applications) == 1
    assert loaded.applications[0].company == "Example Co"
    assert loaded.applications[0].job_title == "Engineer"
    assert loaded.applications[0].url == "https://example.com/jobs/1"


def test_new_record_generates_uuid():
    """new_record() creates records with unique UUIDs."""
    r1 = new_record("https://a.com", "A", "Eng")
    r2 = new_record("https://b.com", "B", "Eng")
    assert r1.id != r2.id
    assert len(r1.id) == 36  # UUID4 format


def test_new_record_default_status():
    """new_record() defaults status to 'in_progress'."""
    r = new_record("https://a.com", "A", "Eng")
    assert r.status == "in_progress"


def test_search_qa_finds_matching(sample_history):
    """search_qa() returns QAPairs whose field_label contains the query."""
    results = search_qa(sample_history, "how did you hear")
    assert len(results) == 2
    assert all("How did you hear" in qa.field_label for qa in results)


def test_search_qa_case_insensitive(sample_history):
    """search_qa() is case-insensitive."""
    results = search_qa(sample_history, "HOW DID YOU HEAR")
    assert len(results) == 2


def test_search_qa_with_company_filter(sample_history):
    """search_qa() scopes results to the given company."""
    results = search_qa(sample_history, "how did you hear", company="Acme Corp")
    assert len(results) == 1
    assert results[0].answer == "LinkedIn"


def test_search_qa_company_filter_case_insensitive(sample_history):
    """search_qa() company filter is case-insensitive."""
    results = search_qa(sample_history, "how did you hear", company="acme corp")
    assert len(results) == 1


def test_search_qa_no_results(sample_history):
    """search_qa() returns empty list when nothing matches."""
    results = search_qa(sample_history, "nonexistent field xyz")
    assert results == []


def test_lookup_answer_returns_most_recent(sample_history):
    """lookup_answer() returns the last matching QAPair (most recent)."""
    result = lookup_answer(sample_history, "how did you hear")
    # Beta Inc record is last, so its "Referral" answer should be returned
    assert result is not None
    assert result.answer == "Referral"


def test_lookup_answer_with_company_scope(sample_history):
    """lookup_answer() with company scopes the lookup."""
    result = lookup_answer(sample_history, "how did you hear", company="Acme Corp")
    assert result is not None
    assert result.answer == "LinkedIn"


def test_lookup_answer_verified_only_filter(sample_history):
    """lookup_answer() with verified_only=True excludes unverified answers."""
    # cover letter is unverified in sample_history
    result = lookup_answer(sample_history, "cover letter", verified_only=True)
    assert result is None

    result = lookup_answer(sample_history, "cover letter", verified_only=False)
    assert result is not None
    assert result.answer == "I am excited to apply..."


def test_lookup_answer_no_match(sample_history):
    """lookup_answer() returns None when no match is found."""
    result = lookup_answer(sample_history, "some completely unknown field")
    assert result is None


def test_save_history_creates_directory(tmp_path, monkeypatch):
    """save_history() creates the directory if it doesn't exist."""
    import autoapply.services.history_store as hs
    new_dir = tmp_path / "new_history_dir"
    hs.AUTOAPPLY_DIR = new_dir
    hs.HISTORY_FILE = new_dir / "history.json"
    h = ApplicationHistory()
    save_history(h)
    assert hs.HISTORY_FILE.exists()


def test_history_with_qa_pairs_roundtrip():
    """Full QAPair data survives save/load roundtrip."""
    h = ApplicationHistory()
    record = ApplicationRecord(
        id="test-id-001",
        url="https://test.com",
        company="TestCo",
        job_title="Dev",
        applied_at="2026-01-01T00:00:00+00:00",
        status="submitted",
        qa_pairs=[
            QAPair(
                field_label="First Name",
                normalized_key="personal.first_name",
                field_type="text",
                answer="Jane",
                source="profile",
                company="TestCo",
                user_verified=True,
            )
        ],
    )
    h = add_record(h, record)
    save_history(h)

    loaded = load_history()
    qa = loaded.applications[0].qa_pairs[0]
    assert qa.field_label == "First Name"
    assert qa.normalized_key == "personal.first_name"
    assert qa.answer == "Jane"
    assert qa.user_verified is True
