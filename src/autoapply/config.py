import os
from pathlib import Path

AUTOAPPLY_DIR = Path(os.environ.get("AUTOAPPLY_DIR", Path.home() / ".autoapply"))
PROFILE_FILE = AUTOAPPLY_DIR / "profile.json"
HISTORY_FILE = AUTOAPPLY_DIR / "history.json"
SESSIONS_DIR = AUTOAPPLY_DIR / "sessions"  # Browser cookie sessions, one file per ATS platform
