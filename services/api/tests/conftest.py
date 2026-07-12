import os
import tempfile
from pathlib import Path


TEST_DB_PATH = Path(tempfile.mkdtemp(prefix="novel-local-ai-tests-")) / "test_novel.db"
os.environ["NOVEL_AI_DB_URL"] = "sqlite:///{}".format(TEST_DB_PATH)
