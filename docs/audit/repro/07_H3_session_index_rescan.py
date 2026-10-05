import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from shopify_tool.session_manager import SessionManager

root = Path(tempfile.mkdtemp())
class PM:
    def get_sessions_root(self): return root
    def invalidate_metadata_cache(self, *a): pass
d = root / "CLIENT_A"
for i in range(3):
    s = d / f"2026-10-0{i+1}_1"; s.mkdir(parents=True)
    (s / "session_info.json").write_text(json.dumps({"session_name": s.name, "created_at": s.name, "statistics": {}, "status": "active"}))
(d / "stray_folder").mkdir()   # a dir with no session_info.json

sm = SessionManager(PM())
scans = 0
orig = sm._scan_sessions
def counting(p):
    global scans; scans += 1; return orig(p)
sm._scan_sessions = counting
for _ in range(5):
    sm.list_client_sessions("A")
print("full rescans over 5 list calls:", scans)
