"""طبقة الحماية المشتركة: تنظيف النصوص قبل وضعها في الصفحات، والتحقق من الروابط.

كل نص يدخل صفحة HTML لازم يمر من esc()، وكل رابط خارجي لازم يمر من check_url().
لو رابط ما عداش التحقق، البناء يوقف ويطلع خطأ واضح بدل ما ينشر رابط مشبوه.
"""
from __future__ import annotations

import html
import ipaddress
import re
from urllib.parse import quote, urlsplit, urlunsplit

# النطاقات المسموح بيها. أي رابط برّا هذي القائمة يرفضه البناء.
# المطابقة على حدود النقاط فقط: "gov.ly" تقبل "cbl.gov.ly" وترفض "evilgov.ly" و "gov.ly.evil.com".
ALLOWED_SUFFIXES = (
    "gov.ly",
    "edu.ly",
    "mosa.ly",
    "noc.ly",
    "hnec.ly",
    "ldl.ly",
    "qaa.ly",
    "ndb.ly",
)
# نطاقات مش ليبية رسمية لكنها مضافة عمداً، كل وحدة بمسار محدد.
ALLOWED_EXACT = {
    "www.mhedusr.com": "/",                      # وزارة التعليم العالي (بنغازي) على نطاق .com
    "play.google.com": "/store/apps/details",    # تطبيق زكاة ليبيا الرسمي
}

ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$")


class UnsafeURL(ValueError):
    """رابط مرفوض لأسباب أمنية."""


def esc(value: object) -> str:
    """تحويل أي قيمة لنص آمن داخل HTML (بما فيه داخل الخصائص بين علامتي تنصيص)."""
    return html.escape("" if value is None else str(value), quote=True)


def host_allowed(host: str, extra_hosts: tuple[str, ...] = ()) -> bool:
    host = host.lower().rstrip(".")
    if host in extra_hosts:
        return True
    if host in ALLOWED_EXACT:
        return True
    return any(host == s or host.endswith("." + s) for s in ALLOWED_SUFFIXES)


def check_url(url: str, *, extra_hosts: tuple[str, ...] = (), allow_http: bool = False) -> str:
    """يتحقق من الرابط ويرجعه بصيغة آمنة (مشفّرة) للاستخدام في href.

    يرفض: أي بروتوكول غير https، الروابط بأسماء مستخدمين (user@host)، المنافذ،
    عناوين IP، أحرف التحكم، والنطاقات اللي مش في القائمة المسموحة.
    """
    if not isinstance(url, str) or not url or len(url) > 500:
        raise UnsafeURL("الرابط فاضي أو طويل بزاف")
    if any(ord(c) < 0x20 or c in " \\<>\"'`" for c in url):
        raise UnsafeURL(f"الرابط فيه أحرف ممنوعة: {url!r}")

    parts = urlsplit(url)
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if parts.scheme.lower() not in allowed_schemes:
        raise UnsafeURL(f"البروتوكول لازم يكون https: {url!r}")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeURL(f"روابط فيها اسم مستخدم ممنوعة: {url!r}")
    host = parts.hostname or ""
    if not host or not host.isascii():
        raise UnsafeURL(f"اسم النطاق غير صالح: {url!r}")
    if parts.port is not None and host not in extra_hosts:
        raise UnsafeURL(f"المنافذ المخصصة ممنوعة: {url!r}")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip and host not in extra_hosts:
        raise UnsafeURL(f"عناوين IP ممنوعة: {url!r}")
    if not host_allowed(host, extra_hosts):
        raise UnsafeURL(f"النطاق مش في القائمة المسموحة: {host}")
    exact_path = ALLOWED_EXACT.get(host.lower())
    if exact_path and not (parts.path or "/").startswith(exact_path):
        raise UnsafeURL(f"المسار مش مسموح لهذا النطاق: {url!r}")

    # تشفير المسار والاستعلام (مثلاً الحروف العربية في الرابط) بدون كسر الرموز العادية
    path = quote(parts.path, safe="/-._~%!$&'()*+,;=:@")
    query = quote(parts.query, safe="=&-._~%+")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def display_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()
