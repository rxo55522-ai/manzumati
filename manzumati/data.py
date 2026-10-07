"""قراءة ملفات البيانات والتحقق الصارم منها قبل البناء.

أي غلطة في الملف (حقل ناقص، نوع غلط، معرّف فيه رموز، رابط مشبوه) توقف البناء
برسالة واضحة، عشان ما ينشرش الموقع ببيانات خربانة.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .safety import ID_RE, UnsafeURL, check_url

GROUPS = {
    "citizen": ("للمواطن", "المنح، المرتبات، حجز العملة، الحج، والشكاوى"),
    "students": ("للطلاب", "النتائج، الجامعات، ومعادلة الشهادات"),
    "business": ("للشركات", "السجل التجاري، الضرائب، والجمارك"),
}
MAX_TEXT = 600


class DataError(ValueError):
    pass


@dataclass
class Step:
    title: str
    text: str


@dataclass
class System:
    id: str
    name: str
    agency: str
    url: str
    safe_url: str
    group: str
    prepare: str | None
    conditions: str | None
    steps: list[Step]
    registration_closed: bool
    hidden: bool
    popular: bool
    keywords: list[str] = field(default_factory=list)
    state: str = "unknown"        # up / down / suspicious / unknown
    checked_at: str | None = None


@dataclass
class Site:
    systems: list[System] = field(default_factory=list)

    def visible(self) -> list[System]:
        return [s for s in self.systems if not s.hidden]


def _text(obj: dict, key: str, sid: str, *, required: bool = True) -> str | None:
    val = obj.get(key)
    if val is None and not required:
        return None
    if not isinstance(val, str) or not val.strip():
        raise DataError(f"[{sid}] الحقل '{key}' لازم يكون نص مش فاضي")
    if len(val) > MAX_TEXT:
        raise DataError(f"[{sid}] الحقل '{key}' أطول من {MAX_TEXT} حرف")
    return val.strip()


def _bool(obj: dict, key: str, sid: str) -> bool:
    val = obj.get(key, False)
    if not isinstance(val, bool):
        raise DataError(f"[{sid}] الحقل '{key}' لازم يكون true أو false")
    return val


def load_site(data_dir: Path, *, extra_hosts: tuple[str, ...] = (), allow_http: bool = False) -> Site:
    raw = json.loads((data_dir / "systems.json").read_text(encoding="utf-8"))
    status_path = data_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    if not isinstance(raw, dict) or not isinstance(raw.get("systems"), list):
        raise DataError("systems.json لازم يحتوي قائمة 'systems'")

    site = Site()
    seen: set[str] = set()
    for i, obj in enumerate(raw["systems"]):
        if not isinstance(obj, dict):
            raise DataError(f"العنصر رقم {i} مش كائن")
        sid = obj.get("id")
        if not isinstance(sid, str) or not ID_RE.match(sid):
            raise DataError(f"العنصر رقم {i}: المعرّف '{sid}' غير صالح (حروف إنجليزية صغيرة وأرقام وشرطة فقط)")
        if sid in seen:
            raise DataError(f"المعرّف '{sid}' مكرر")
        seen.add(sid)

        group = obj.get("group")
        if group not in GROUPS:
            raise DataError(f"[{sid}] القسم '{group}' غير معروف")
        url = _text(obj, "url", sid)
        try:
            safe_url = check_url(url, extra_hosts=extra_hosts, allow_http=allow_http)
        except UnsafeURL as e:
            raise DataError(f"[{sid}] {e}") from None

        steps_raw = obj.get("steps") or []
        if not isinstance(steps_raw, list) or len(steps_raw) > 15:
            raise DataError(f"[{sid}] الخطوات لازم تكون قائمة (15 خطوة كحد أقصى)")
        steps = [Step(_text(s, "title", sid), _text(s, "text", sid)) for s in steps_raw if isinstance(s, dict)]
        if len(steps) != len(steps_raw):
            raise DataError(f"[{sid}] كل خطوة لازم يكون فيها title و text")

        kw = obj.get("keywords") or []
        if not isinstance(kw, list) or len(kw) > 25 or not all(isinstance(k, str) and 0 < len(k) <= 40 for k in kw):
            raise DataError(f"[{sid}] كلمات البحث لازم تكون قائمة نصوص قصيرة (25 كلمة كحد أقصى)")

        st = status.get(sid, {}) if isinstance(status, dict) else {}
        state = st.get("state") if st.get("state") in ("up", "down", "suspicious") else "unknown"
        checked = st.get("checked_at") if isinstance(st.get("checked_at"), str) else None

        site.systems.append(System(
            id=sid,
            name=_text(obj, "name", sid),
            agency=_text(obj, "agency", sid),
            url=url,
            safe_url=safe_url,
            group=group,
            prepare=_text(obj, "prepare", sid, required=False),
            conditions=_text(obj, "conditions", sid, required=False),
            steps=steps,
            registration_closed=_bool(obj, "registration_closed", sid),
            hidden=_bool(obj, "hidden", sid),
            popular=_bool(obj, "popular", sid),
            keywords=[k.strip() for k in kw],
            state=state,
            checked_at=checked,
        ))
    return site
