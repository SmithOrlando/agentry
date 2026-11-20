"""The API docs must stay complete: every route documented, every request field the handlers read listed."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_api_docs_cover_every_route_and_field():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_api_docs.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
