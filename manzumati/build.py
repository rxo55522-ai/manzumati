"""مولّد الموقع: يقرأ البيانات ويطلع صفحات HTML ثابتة جاهزة للنشر.

الموقع كله صفحات ثابتة: ما فيه قاعدة بيانات، ولا لوحة دخول، ولا كود يشتغل على السيرفر
وقت ما الزائر يفتح الصفحة. هذا يسكّر أغلب أبواب الاختراق المعروفة من الأساس.

الاستخدام:
    python -m manzumati.build --out /var/www/manzumati
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .data import GROUPS, DataError, Site, System, load_site
from .safety import display_host, esc

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# نفس السياسة موجودة كترويسة في nginx؛ هنا نسخة احتياطية داخل الصفحة نفسها.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
       "img-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; "
       "upgrade-insecure-requests")

MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
          "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

LOGO = ('<svg class="logo-mark" width="42" height="42" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
        '<rect width="64" height="64" rx="16" class="lg-bg"/>'
        '<path d="M19 48V29a13 13 0 0 1 26 0v19" class="lg-line"/>'
        '<path d="M14 48h36" class="lg-line"/>'
        '<circle cx="32" cy="37" r="4.5" class="lg-dot"/></svg>')

ICON_ARROW = ('<svg width="20" height="20" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
              '<path d="M15 6l-6 6 6 6"/></svg>')
ICON_BACK = ('<svg width="18" height="18" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
             '<path d="M9 6l6 6-6 6"/></svg>')
ICON_CHECK = ('<svg width="24" height="24" viewBox="0 0 24 24" class="ic ic-ok" aria-hidden="true" focusable="false">'
              '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/></svg>')
ICON_RETRY = ('<svg width="20" height="20" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
              '<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/></svg>')
ICON_SEARCH = ('<svg width="22" height="22" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
               '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>')
ICON_MEGAPHONE = ('<svg width="22" height="22" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
                  '<path d="M4 10v4a1 1 0 0 0 1 1h2l5 4V5L7 9H5a1 1 0 0 0-1 1z"/>'
                  '<path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/></svg>')
ICON_SEND = ('<svg width="22" height="22" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false">'
             '<path d="M21 3L3 10.5l7 2.5 2.5 7L21 3z"/><path d="M10 13l4.5-4.5"/></svg>')
GROUP_ICONS = {
    "citizen": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0",
    "students": "M3 9l9-5 9 5-9 5-9-5zM7 11.5V16c0 1.5 2.5 3 5 3s5-1.5 5-3v-4.5",
    "business": "M4 20V8l8-4 8 4v12M9 20v-6h6v6M4 20h16",
}


# ---------- أدوات العرض ----------

def fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(timezone(timedelta(hours=config.TIMEZONE_OFFSET_HOURS)))
    return f"{local.day} {MONTHS[local.month - 1]}، الساعة {local:%H:%M}"


def status_of(s: System) -> tuple[str, str]:
    """يرجع (الصنف، النص) لحالة المنظومة."""
    if s.state == "suspicious":
        return "warn", "قيد المراجعة"
    if s.state == "down":
        return "down", "واقفة الآن"
    if s.registration_closed:
        return "closed", "التسجيل مقفل"
    if s.state == "up":
        return "up", "شغالة الآن"
    return "closed", "لم تُفحص بعد"


def facebook_url() -> str | None:
    url = config.FACEBOOK_URL.strip()
    if not url:
        return None
    if not re.fullmatch(r"https://www\.facebook\.com/[A-Za-z0-9.\-_/?=]{1,120}", url):
        raise DataError("FACEBOOK_URL لازم يكون رابط صفحة فيسبوك يبدأ بـ https://www.facebook.com/")
    return url


def telegram_url() -> str | None:
    url = config.TELEGRAM_URL.strip()
    if not url:
        return None
    if not re.fullmatch(r"https://t\.me/[A-Za-z][A-Za-z0-9_]{4,31}", url):
        raise DataError("TELEGRAM_URL لازم يكون رابط قناة يبدأ بـ https://t.me/ وبعده اسم القناة بس")
    return url


def canonical(path: str) -> str:
    """الرابط الرسمي للصفحة (بدون .html، لأن Cloudflare يشيلها)."""
    path = path.removesuffix(".html")
    if path in ("index", ""):
        path = ""
    return f"{config.SITE_URL}/{path}"


def jsonld(obj: dict) -> str:
    """بيانات منظمة لقوقل. هذي مش كود يتنفذ، والمتصفح ما يشغلهاش.
    نمنعو أي "<" داخلها باش ما يقدر حد يسكّر الوسم ويحط كود."""
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">{data}</script>'


DEFAULT_DESC = "كل منظومات الدولة الليبية في مكان واحد: الرابط الرسمي، المنظومة شغالة ولا واقفة، وشن تجهز قبل ما تدخل."


def page(title: str, body: str, *, depth: int = 0, description: str = "", path: str = "index.html",
         structured: dict | None = None, noindex: bool = False) -> str:
    base = "../" * depth
    desc = description or DEFAULT_DESC
    url = canonical(path)
    og_img = f"{config.SITE_URL}/img/og.png"
    verify = (f'\n<meta name="google-site-verification" content="{esc(config.GOOGLE_SITE_VERIFICATION)}">'
              if config.GOOGLE_SITE_VERIFICATION and re.fullmatch(r"[A-Za-z0-9_\-]{10,100}", config.GOOGLE_SITE_VERIFICATION) else "")
    robots = '\n<meta name="robots" content="noindex">' if noindex else ""
    ld = ("\n" + jsonld(structured)) if structured else ""
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">{robots}{verify}
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(config.SITE_NAME)}">
<meta property="og:locale" content="ar_LY">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(og_img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="منظومتي: كل منظومات الدولة في مكان واحد">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0E5A4A">
<link rel="icon" href="{base}img/favicon.svg" type="image/svg+xml">
<link rel="icon" href="{base}img/icon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="{base}img/apple-touch-icon.png">
<link rel="manifest" href="{base}manifest.webmanifest">
<meta name="apple-mobile-web-app-title" content="{esc(config.SITE_NAME)}">
<link rel="stylesheet" href="{base}css/site.css">
<script src="{base}js/site.js" defer></script>{ld}
</head>
<body>
<a class="skip" href="#main">تخطّى للمحتوى</a>
{header(depth)}
{body}
{footer(depth)}
</body>
</html>
"""


def header(depth: int) -> str:
    base = "../" * depth
    nav = "" if depth == 0 else f'<a class="pill" href="{base}index.html">{ICON_BACK}الرئيسية</a>'
    if depth == 0:
        nav = f'<a class="pill pill-plain" href="all.html">كل المنظومات</a><a class="pill" href="about.html">عن منظومتي</a>'
    return f"""<header class="site-header wrap">
  <a class="brand" href="{base}index.html">{LOGO}<span>{esc(config.SITE_NAME)}</span></a>
  <nav class="nav" aria-label="القائمة الرئيسية">{nav}</nav>
</header>"""


def footer(depth: int) -> str:
    base = "../" * depth
    return f"""<footer class="site-footer">
  <div class="wrap footer-in">
    <p>منظومتي دليل للمنظومات الحكومية الليبية، والخدمات نفسها تقدمها الجهات الرسمية عبر روابطها.</p>
    <nav aria-label="روابط أسفل الصفحة"><a href="{base}about.html">عن منظومتي</a><a href="{base}about.html#contact">بلّغ عن مشكلة</a></nav>
  </div>
</footer>"""


def status_pill(s: System) -> str:
    cls, label = status_of(s)
    return f'<span class="status st-{cls}"><span class="dot"></span>{esc(label)}</span>'


def system_row(s: System, depth: int) -> str:
    base = "../" * depth
    cls, _ = status_of(s)
    search = " ".join([s.name, s.agency, display_host(s.url), *s.keywords])
    return (f'<li data-state="{esc(cls)}" data-search="{esc(search)}">'
            f'<a class="row" href="{base}s/{esc(s.id)}.html">'
            f'<span class="row-text"><span class="row-name">{esc(s.name)}</span>'
            f'<span class="row-agency">{esc(s.agency)}</span></span>{status_pill(s)}</a></li>')


def fb_band(depth: int) -> str:
    """قسم المتابعة: قناة التنبيهات على تيليجرام + صفحة الفيسبوك."""
    fb, tg = facebook_url(), telegram_url()
    if not fb and not tg:
        return ""
    if tg:
        title = "ما تقعدش تجرّب كل شوية"
        text = "اشترك في قناتنا على تيليجرام، ونبلغوك أول ما منظومتك ترجع تخدم."
    else:
        title = "تابع صفحتنا على فيسبوك"
        text = "أول ما تفتح منظومة أو تتغير حاجة فيها، تلقاها عندنا في الصفحة."
    btns = ""
    if tg:
        btns += f'<a class="btn btn-gold" href="{esc(tg)}" rel="noopener noreferrer">{ICON_SEND}اشترك في القناة</a>'
    if fb:
        cls = "btn btn-ghost" if tg else "btn btn-gold"
        btns += f'<a class="{cls}" href="{esc(fb)}" rel="noopener noreferrer">{ICON_MEGAPHONE}صفحتنا على فيسبوك</a>'
    return f"""<section class="band" aria-labelledby="fbh">
  <div class="band-text"><h2 id="fbh">{esc(title)}</h2>
  <p>{esc(text)}</p></div>
  <div class="band-actions">{btns}</div>
</section>"""


# ---------- الصفحات ----------

def render_index(site: Site) -> str:
    popular = [s for s in site.visible() if s.popular]
    cards = "".join(
        f'<li><a class="card-link" href="s/{esc(s.id)}.html"><span class="card-text">'
        f'<span class="card-name">{esc(s.name)}</span>{status_pill(s)}</span>'
        f'<span class="round">{ICON_ARROW}</span></a></li>' for s in popular)
    groups = "".join(
        f'<li><a class="group-card" href="{g}.html"><span class="group-icon">'
        f'<svg width="26" height="26" viewBox="0 0 24 24" class="ic" aria-hidden="true" focusable="false"><path d="{GROUP_ICONS[g]}"/></svg></span>'
        f'<span class="group-title">{esc(t)}</span><span class="group-desc">{esc(d)}</span></a></li>'
        for g, (t, d) in GROUPS.items())
    body = f"""<main id="main">
<section class="wrap"><div class="hero">
  <span class="rule"></span>
  <h1>كل منظومات الدولة في مكان واحد</h1>
  <p class="lead">شن المنظومة اللي تدور عليها؟</p>
  <form class="search" role="search" action="all.html" method="get">
    <label class="sr" for="q">دوّر على منظومة</label>
    {ICON_SEARCH}
    <input id="q" name="q" type="search" maxlength="60" autocomplete="off">
    <button type="submit">دوّر</button>
  </form>
</div></section>
<div class="wrap stack">
  <section aria-labelledby="pop"><h2 id="pop">الأكثر استخداماً</h2><ul class="cards">{cards}</ul></section>
  <section aria-labelledby="cats"><h2 id="cats">اختار القسم</h2><ul class="groups">{groups}</ul></section>
  {fb_band(0)}
</div>
</main>"""
    return page(f"{config.SITE_NAME} | كل منظومات الدولة الليبية في مكان واحد", body, path="index.html",
                structured={"@context": "https://schema.org", "@type": "WebSite", "name": config.SITE_NAME,
                            "url": f"{config.SITE_URL}/", "inLanguage": "ar", "description": DEFAULT_DESC})


def render_list_page(site: Site, *, title: str, lead: str, systems: list[System], with_search: bool,
                     path: str = "all.html") -> str:
    rows = "".join(system_row(s, 0) for s in systems)
    search = ""
    if with_search:
        search = f"""<form class="search search-sm" role="search" action="all.html" method="get">
    <label class="sr" for="q">دوّر على منظومة</label>{ICON_SEARCH}
    <input id="q" name="q" type="search" maxlength="60" autocomplete="off"><button type="submit">دوّر</button></form>"""
    body = f"""<main id="main" class="wrap stack-sm">
<section class="panel head-panel">
  <span class="rule"></span><h1>{esc(title)}</h1><p class="lead">{esc(lead)}</p>
  {search}
  <div class="filters" role="group" aria-label="اعرض حسب الحالة" data-filters hidden>
    <button type="button" class="chip" data-filter="all" aria-pressed="true">الكل</button>
    <button type="button" class="chip" data-filter="up" aria-pressed="false">الشغالة بس</button>
    <button type="button" class="chip" data-filter="down" aria-pressed="false">الواقفة</button>
  </div>
</section>
<section class="panel list-panel" aria-label="قائمة المنظومات">
  <ul class="rows" data-list>{rows}</ul>
  <p class="empty" data-empty hidden>ما لقيناش منظومة بهذا الاسم. جرّب كلمة ثانية.</p>
</section>
</main>"""
    names = "، ".join(x.name for x in systems[:4])
    return page(f"{title}: المنظومات الحكومية الليبية | {config.SITE_NAME}", body, path=path,
                description=f"{lead} {names}، وغيرها: الرابط الرسمي لكل منظومة وحالتها الآن."[:300])


def render_system(s: System) -> str:
    cls, label = status_of(s)
    host = display_host(s.url)
    checked = fmt_time(s.checked_at)
    checked_line = f'<span class="muted">آخر فحص: {esc(checked)}</span>' if checked else ""

    alert = ""
    enter_btn = (f'<a class="btn btn-primary btn-wide" href="{esc(s.safe_url)}" rel="noopener noreferrer">'
                 f'ادخل للمنظومة{ICON_ARROW}</a>')
    tg = telegram_url()
    tg_line = (f'<p class="alert-tg">ما تقعدش تجرّب كل شوية: <a href="{esc(tg)}" rel="noopener noreferrer">'
               f'اشترك في القناة</a> ونبلغوك أول ما ترجع.</p>') if tg else ""
    if cls == "down":
        alert = f"""<section class="alert alert-down">
  <div><h2>المنظومة واقفة الآن</h2>
  <p>المشكلة مش منك، المنظومة نفسها متردش حالياً، وهذا يصير هلبا لما يكون عليها ضغط. استنى شوية وجرّب مرة ثانية.</p>
  {checked_line}{tg_line}</div>
  <a class="btn btn-primary" href="{esc(s.safe_url)}" rel="noopener noreferrer">{ICON_RETRY}جرّب مرة ثانية</a>
</section>"""
        enter_btn = ""
    elif cls == "warn":
        alert = """<section class="alert alert-warn"><div><h2>الرابط تحت المراجعة</h2>
  <p>لاحظنا إن رابط هذي المنظومة صار يحوّل لموقع مش رسمي، فوقفنا عرضه لحمايتك لين نتأكدو منه.</p></div></section>"""
        enter_btn = ""

    prep = ""
    if s.prepare:
        text, note = s.prepare.strip(), ""
        head, colon, rest = text.partition(":")
        if colon and len(head) <= 25 and head.startswith("حسب"):
            text, note = rest.strip(), head.strip()
        items = [p.strip() for p in re.split(r"[،,]| و(?=ال|رقم)", text.rstrip(".")) if p.strip()]
        # نعرضها كقائمة بس لو هي فعلاً أشياء قصيرة تتجهز؛ غير هذا تبقى فقرة عادية
        as_list = len(items) > 1 and ":" not in text and "." not in text.rstrip(".") \
            and all(len(p) <= 45 for p in items)
        if as_list:
            lis = "".join(f"<li>{ICON_CHECK}<span>{esc(p)}</span></li>" for p in items)
            body_html = f'<ul class="checks">{lis}</ul>'
        else:
            body_html = f"<p>{esc(text)}</p>"
        note_html = f'<p class="muted small">{esc(note)}.</p>' if note else ""
        cond = f'<p class="muted sep">{esc(s.conditions)}</p>' if s.conditions else ""
        prep = f'<h2>جهّز قبل ما تدخل</h2>{body_html}{note_html}{cond}'
    else:
        prep = '<h2>جهّز قبل ما تدخل</h2><p class="muted">نكمّلو هذي المعلومات قريباً.</p>'

    steps = ""
    if s.steps:
        lis = "".join(
            f'<li><span class="num">{i}</span><span class="step-text"><span class="step-title">{esc(st.title)}</span>'
            f'<span class="step-body">{esc(st.text)}</span></span></li>' for i, st in enumerate(s.steps, 1))
        steps = f"""<section class="panel steps-panel" aria-labelledby="how"><h2 id="how">كيف تستخدمها؟</h2>
  <ol class="steps">{lis}</ol><p class="muted small">الخطوات حسب مصادر منشورة، ونحدّثوها أول ما يتغير شيء.</p></section>"""

    official = "" if cls == "warn" else f'<p class="official">الموقع الرسمي: <bdi dir="ltr">{esc(host)}</bdi></p>'
    body = f"""<main id="main" class="wrap stack-sm">
<section class="panel head-panel">
  <span class="rule"></span><h1>{esc(s.name)}</h1>
  <div class="meta"><span class="agency">{esc(s.agency)}</span>{status_pill(s)}</div>
</section>
{alert}
<div class="split{' split-single' if not steps else ''}">
  {steps}
  <aside class="panel side">{prep}{enter_btn}{official}</aside>
</div>
{fb_band(1)}
</main>"""
    gtitle = GROUPS[s.group][0]
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": config.SITE_NAME, "item": f"{config.SITE_URL}/"},
        {"@type": "ListItem", "position": 2, "name": gtitle, "item": canonical(f"{s.group}.html")},
        {"@type": "ListItem", "position": 3, "name": s.name, "item": canonical(f"s/{s.id}.html")},
    ]}
    return page(f"{s.name}: الرابط الرسمي وحالتها الآن | {config.SITE_NAME}", body, depth=1, path=f"s/{s.id}.html",
                description=f"{s.name} من {s.agency}: الرابط الرسمي، المنظومة شغالة ولا واقفة الآن، وشن تجهز قبل ما تدخل.",
                structured=crumbs)


def render_about() -> str:
    contact = (f'<p>للتواصل والإعلانات: <bdi dir="ltr">{esc(config.CONTACT_EMAIL)}</bdi></p>'
               if config.CONTACT_EMAIL else "")
    fb = facebook_url()
    fb_line = (f'<p>تعرف منظومة مش موجودة عندنا، أو لقيت رابط غلط؟ ابعتلنا رسالة على '
               f'<a href="{esc(fb)}" rel="noopener noreferrer">صفحتنا في فيسبوك</a>.</p>') if fb else \
              '<p>تعرف منظومة مش موجودة عندنا، أو لقيت رابط غلط؟ ابعتلنا رسالة على صفحتنا في فيسبوك.</p>'
    tg = telegram_url()
    if tg:
        fb_line += (f'<p>وباش يوصلك تنبيه لما منظومة توقف أو ترجع تخدم، اشترك في '
                    f'<a href="{esc(tg)}" rel="noopener noreferrer">قناة التنبيهات على تيليجرام</a>.</p>')
    body = f"""<main id="main" class="wrap stack-sm">
<section class="panel head-panel">
  <span class="rule"></span><h1>عن منظومتي</h1>
  <p class="lead">منظومتي دليل يجمع المنظومات الحكومية الليبية في مكان واحد، عشان توصل للرابط الرسمي الصحيح وتعرف إذا كانت المنظومة شغالة قبل ما تتعب روحك.</p>
  <ul class="facts">
    <li><b>نفحصوها باستمرار</b><span>كل منظومة نجربوها كل كم دقيقة.</span></li>
    <li><b>روابط رسمية بس</b><span>منحطوش إلا روابط الجهات الحكومية نفسها.</span></li>
    <li><b>منطلبوش أي بيانات</b><span>بياناتك تدخلها في موقع الجهة الرسمية فقط.</span></li>
  </ul>
</section>
<section class="panel" id="contact"><h2>اقترح منظومة أو بلّغ عن مشكلة</h2>{fb_line}{contact}
  <p class="muted">لا تبعت رقمك الوطني ولا أي بيانات شخصية.</p></section>
</main>"""
    return page(f"عن منظومتي | {config.SITE_NAME}", body, path="about.html")


def render_404() -> str:
    body = """<main id="main" class="wrap stack-sm"><section class="panel head-panel">
<span class="rule"></span><h1>الصفحة مش موجودة</h1>
<p class="lead">ممكن الرابط فيه غلطة، أو الصفحة تنقلت.</p>
<a class="btn btn-primary" href="/index.html">رجوع للرئيسية</a></section></main>"""
    return page(f"الصفحة مش موجودة | {config.SITE_NAME}", body, noindex=True).replace('href="img/', 'href="/img/').replace(
        'href="css/', 'href="/css/').replace('src="js/', 'src="/js/').replace('href="index.html"', 'href="/index.html"').replace(
        'href="all.html"', 'href="/all.html"').replace('href="about.html', 'href="/about.html').replace(
        'href="manifest.webmanifest"', 'href="/manifest.webmanifest"')


# ---------- البناء ----------

def build(out_dir: Path, data_dir: Path, *, extra_hosts: tuple[str, ...] = (), allow_http: bool = False) -> Path:
    site = load_site(data_dir, extra_hosts=extra_hosts, allow_http=allow_http)
    facebook_url()  # يتحقق من الروابط قبل ما نبنو أي صفحة
    telegram_url()

    out_dir.mkdir(parents=True, exist_ok=True)
    releases = out_dir / "releases"
    releases.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".build-", dir=releases))
    try:
        files: dict[str, str] = {
            "index.html": render_index(site),
            "all.html": render_list_page(site, title="كل المنظومات", lead="دوّر بالاسم أو اختار من القائمة.",
                                         systems=site.visible(), with_search=True),
            "about.html": render_about(),
            "404.html": render_404(),
        }
        for g, (t, d) in GROUPS.items():
            files[f"{g}.html"] = render_list_page(site, title=t, lead=d + ".",
                                                  systems=[s for s in site.visible() if s.group == g], with_search=False,
                                                  path=f"{g}.html")
        for s in site.visible():
            files[f"s/{s.id}.html"] = render_system(s)

        for rel, content in files.items():
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        shutil.copytree(STATIC, tmp, dirs_exist_ok=True)
        (tmp / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {config.SITE_URL}/sitemap.xml\n", encoding="utf-8")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        urls = [canonical(p) for p in files if p != "404.html"]
        (tmp / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
            + "</urlset>\n", encoding="utf-8")
        for root, dirs, fnames in os.walk(tmp):
            for d in dirs:
                os.chmod(Path(root) / d, 0o755)
            for f in fnames:
                os.chmod(Path(root) / f, 0o644)

        # تبديل ذري: الزائر يشوف إما النسخة القديمة كاملة أو الجديدة كاملة، ما يشوفش نص نسخة
        final = releases / time.strftime("%Y%m%d-%H%M%S")
        n = 1
        while final.exists():
            final = releases / (time.strftime("%Y%m%d-%H%M%S") + f"-{n}")
            n += 1
        tmp.rename(final)
        link_tmp = out_dir / ".current.tmp"
        if link_tmp.is_symlink() or link_tmp.exists():
            link_tmp.unlink()
        try:
            link_tmp.symlink_to(final.relative_to(out_dir), target_is_directory=True)
            os.replace(link_tmp, out_dir / "current")
        except OSError:
            # ويندوز ما يسمحش بالروابط الرمزية في العادة: ننسخو النسخة لمجلد current بدلها
            # (هذا للتجربة على الجهاز بس؛ السيرفر يستعمل الطريقة الذرية فوق)
            current = out_dir / "current"
            if current.is_symlink() or current.is_file():
                current.unlink()
            elif current.exists():
                shutil.rmtree(current)
            shutil.copytree(final, current)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    keep = sorted((p for p in releases.iterdir() if p.is_dir() and not p.name.startswith(".")), reverse=True)
    for old in keep[3:]:
        shutil.rmtree(old, ignore_errors=True)
    return out_dir / "current"


def build_flat(out_dir: Path, data_dir: Path) -> Path:
    """بناء في مجلد عادي (بدون نسخ ورابط current) للرفع على Cloudflare Pages."""
    work = Path(tempfile.mkdtemp(prefix="manzumati-build-"))
    try:
        current = build(work, data_dir).resolve()
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(current, out_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="بناء موقع منظومتي")
    ap.add_argument("--out", type=Path, default=ROOT / "public")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--flat", action="store_true", help="مجلد عادي للرفع على Cloudflare Pages")
    args = ap.parse_args(argv)
    try:
        current = build_flat(args.out, args.data) if args.flat else build(args.out, args.data)
    except DataError as e:
        print(f"البناء توقف: {e}", file=sys.stderr)
        return 1
    print(f"تم البناء: {current.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
