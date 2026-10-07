# منظومتي

دليل يجمع المنظومات الحكومية الليبية في مكان واحد: الرابط الرسمي، حالتها الآن، وشن تجهز قبل ما تدخل.

## الملفات

```
data/systems.json     ← بيانات المنظومات (هنا تعدّل وتضيف)
data/status.json      ← حالة كل منظومة (الفاحص يكتبه لحاله)
manzumati/config.py   ← اسم الموقع، الدومين، رابط الفيسبوك
manzumati/build.py    ← يبني صفحات الموقع
manzumati/checker.py  ← يفحص المنظومات كل 5 دقايق
manzumati/safety.py   ← فحص الروابط وتنظيف النصوص
static/               ← التصميم (css) والبحث (js) والشعار والخطوط
deploy/               ← إعدادات السيرفر
tests/                ← اختبارات الحماية
SECURITY.md           ← شرح كل الحماية
```

## تجربة الموقع على جهازك

يحتاج بس Python 3.10 أو أحدث، بدون أي تثبيت ثاني.

```
python3 -m manzumati.build
python3 -m http.server 8000 -d public/current
```
وافتح في المتصفح: http://localhost:8000

## إضافة منظومة جديدة

افتح `data/systems.json` وضيف عنصر بنفس الشكل:

```json
{
  "id": "new-system",
  "name": "اسم المنظومة",
  "agency": "الجهة",
  "url": "https://example.gov.ly/",
  "group": "citizen",
  "prepare": "الرقم الوطني، رقم الهاتف.",
  "steps": [],
  "registration_closed": false,
  "hidden": false,
  "popular": false
}
```

- `id`: حروف إنجليزية صغيرة وأرقام وشرطة بس.
- `group`: `citizen` (للمواطن) أو `students` (للطلاب) أو `business` (للشركات).
- بعدها شغّل البناء. لو فيه غلطة، يقولك وين بالضبط وما ينشرش.

## قبل النشر

1. `bash tools/fetch_fonts.sh` (مرة وحدة، ينزل الخطوط)
2. حط رابط صفحة الفيسبوك والدومين في `manzumati/config.py`
3. `python3 -m unittest -v tests.test_security` (لازم كلها تطلع OK)
4. على السيرفر: `sudo bash deploy/setup-server.sh manzumati.ly`

## النشر المجاني (GitHub + Cloudflare Pages)

- الكود على GitHub، والموقع على Cloudflare Pages ورابطه `manzumati.pages.dev`.
- الملف `.github/workflows/site.yml` يفحص المنظومات كل 5 دقايق، ولو تغيرت حالة منظومة يعاود ينشر الموقع لحاله.
- لما تعدّل `data/systems.json` من GitHub نفسه، الاختبارات تشتغل، ولو نجحت الموقع يتحدث لحاله.
- يحتاج سرّين في إعدادات المستودع: `CLOUDFLARE_API_TOKEN` و `CLOUDFLARE_ACCOUNT_ID`.
- الملاحظات الداخلية عن المنظومات مش في المستودع (لأنه عام)، محفوظة في ملف منفصل عندك.
