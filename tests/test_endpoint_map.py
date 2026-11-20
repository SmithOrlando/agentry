"""Every API call in the Vue app must hit a real Flask route (method + path).

Catches a renamed/removed endpoint or a typo in the frontend without running a browser.
Same check as `python3 scripts/gen_endpoint_map.py --check`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not (ROOT / "frontend" / "src").exists(), reason="frontend sources not present")
def test_every_frontend_call_matches_a_route():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_endpoint_map.py"), "--check"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 unmatched" in r.stdout
