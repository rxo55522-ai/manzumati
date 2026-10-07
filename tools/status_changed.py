"""يقارن حالة المنظومات قبل الفحص وبعده، ويقول لـ GitHub شن يدير.

- deploy=true  لو منظومة تغيرت حالتها (شغالة/واقفة/قيد المراجعة) → نعاودو ننشرو الموقع
- commit=true  لو تغيرت الحالة أو عدد الفشلات، أو مرّ يوم على آخر حفظ → نحفظو status.json
  (الحفظ اليومي يخلي GitHub يعرف إن المشروع حي وما يوقفش الفحص التلقائي)
"""
import json
import subprocess
import sys
import time


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


old, new = load(sys.argv[1]), load(sys.argv[2])
ids = set(old) | set(new)
state_changed = any((old.get(i) or {}).get("state") != (new.get(i) or {}).get("state") for i in ids)
fails_changed = any((old.get(i) or {}).get("fails") != (new.get(i) or {}).get("fails") for i in ids)

try:
    last = int(subprocess.run(["git", "log", "-1", "--format=%ct", "--", "data/status.json"],
                              capture_output=True, text=True, check=True).stdout.strip() or 0)
except (subprocess.CalledProcessError, ValueError):
    last = 0
daily = time.time() - last > 20 * 3600

print(f"deploy={'true' if state_changed else 'false'}")
print(f"commit={'true' if (state_changed or fails_changed or daily) else 'false'}")
