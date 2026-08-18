import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Config.load() requires .env with real values — tests that need Settings
# only (not Secrets) should use Settings.load()/Settings() directly rather
# than Config.load(), so the suite passes on a fresh clone with no .env.
os.environ.setdefault("BOT_TOKEN", "123456:test-token-not-real-aaaaaaaaaaaaaaaaaaaa")
os.environ.setdefault("CHAT_ID", "1")
