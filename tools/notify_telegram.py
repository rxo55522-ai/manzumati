"""يبعت تنبيه لقناة تيليجرام لما منظومة توقف أو ترجع تخدم.

البوت يبعت بس، وما يستقبلش أي رسالة من الناس.

يحتاج سرّين في GitHub:
  TELEGRAM_BOT_TOKEN  مفتاح البوت من BotFather
  TELEGRAM_CHAT_ID    اسم القناة، مثلاً @manzumati_alerts

الاستعمال:
  python tools/notify_telegram.py OLD_STATUS NEW_STATUS
  python tools/notify_telegram.py --test        (رسالة تجربة)
"""
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from manzumati import config  # noqa: E402

# لو تغيرت حالة أكثر من هذا العدد في فحص واحد، غالباً المشكلة في الفاحص نفسه
# (مثلاً انقطع الاتصال)، فما نبعتوش حتى شي باش ما نخوفوش الناس على الفاضي.
MAX_CHANGES = 5


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def send(token, chat, text):
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,                       # نص عادي بدون تنسيق: ما فيش أي مجال لحقن رموز
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:  # ما نطبعوش الرابط لأنه فيه المفتاح
        print(f"تيليجرام رفض الرسالة: {type(e).__name__} {getattr(e, 'code', '')}")
        return False


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("أسرار تيليجرام مش موجودة، نتخطو التنبيهات.")
        return 0

    if sys.argv[1:] == ["--test"]:
        ok = send(token, chat, f"✅ بوت تنبيهات {config.SITE_NAME} شغال.\n{config.SITE_URL}")
        return 0 if ok else 1

    old, new = load(sys.argv[1]), load(sys.argv[2])
    systems = load(os.path.join(ROOT, "data", "systems.json")).get("systems", [])
    names = {s["id"]: s["name"] for s in systems if isinstance(s, dict) and not s.get("hidden")}

    changes = []
    for sid, name in names.items():
        o, n = old.get(sid) or {}, new.get(sid) or {}
        if o.get("source") == "manual":      # أول فحص آلي بعد التعديل اليدوي: ما نعلنوش عليه
            continue
        before, after = o.get("state"), n.get("state")
        if before == after or {before, after} - {"up", "down"}:
            continue                          # نعلنو بس على شغالة ↔ واقفة
        changes.append((sid, name, after))

    if not changes:
        return 0
    if len(changes) > MAX_CHANGES:
        print(f"{len(changes)} تغييرات مع بعض، غالباً مشكلة في الفحص. ما بعتناش تنبيهات.")
        return 0

    for sid, name, state in changes:
        page = f"{config.SITE_URL}/s/{sid}.html"
        if state == "up":
            text = f"🟢 {name}\nرجعت تخدم توا.\n\nالرابط الرسمي وشن تجهز قبل ما تدخل:\n{page}"
        else:
            text = f"🔴 {name}\nواقفة توا. المشكلة مش منك، جرّب بعد شوية.\n\nنبلغوك أول ما ترجع:\n{page}"
        send(token, chat, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
