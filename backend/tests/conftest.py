import os

os.environ.setdefault("SESSION_SECRET", "test-secret-1234567890")
os.environ.setdefault("COLLEGE_PARTICIPANT_KEY", "test-participant-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
