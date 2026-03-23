import json
import uuid
from datetime import datetime, timezone
from autoapply.config import HISTORY_FILE, AUTOAPPLY_DIR
from autoapply.models.history import ApplicationHistory, ApplicationRecord, QAPair


def load_history() -> ApplicationHistory:
    if not HISTORY_FILE.exists():
        return ApplicationHistory()
    with open(HISTORY_FILE) as f:
        data = json.load(f)
    return ApplicationHistory.model_validate(data)


def save_history(history: ApplicationHistory) -> None:
    AUTOAPPLY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history.model_dump(), f, indent=2)


def add_record(history: ApplicationHistory, record: ApplicationRecord) -> ApplicationHistory:
    history.applications.append(record)
    return history


def new_record(url: str, company: str, job_title: str) -> ApplicationRecord:
    return ApplicationRecord(
        id=str(uuid.uuid4()),
        url=url,
        company=company,
        job_title=job_title,
        applied_at=datetime.now(timezone.utc).isoformat(),
    )


def search_qa(history: ApplicationHistory, query: str, company: str | None = None) -> list[QAPair]:
    """Search Q&A pairs by question text, optionally scoped to a company."""
    query_lower = query.lower()
    results = []
    for app in history.applications:
        if company and app.company.lower() != company.lower():
            continue
        for qa in app.qa_pairs:
            if query_lower in qa.field_label.lower():
                results.append(qa)
    return results


def lookup_answer(
    history: ApplicationHistory,
    question: str,
    company: str | None = None,
    verified_only: bool = False,
) -> QAPair | None:
    """Find the most recent matching Q&A pair."""
    matches = search_qa(history, question, company)
    if verified_only:
        matches = [m for m in matches if m.user_verified]
    if not matches:
        return None
    return matches[-1]  # Most recent
