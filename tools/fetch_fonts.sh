#!/usr/bin/env bash
# تنزيل الخطوط وحفظها داخل الموقع نفسه (static/fonts).
# ليش؟ عشان الموقع ما يحمّلش أي شيء من مواقع برّا (سياسة CSP تمنع هذا)،
# وعشان ما نعطوش أي جهة خارجية بيانات زوارنا.
# شغّله مرة وحدة على جهازك أو السيرفر:  bash tools/fetch_fonts.sh
set -euo pipefail
cd "$(dirname "$0")/../static/fonts"

BASE="https://cdn.jsdelivr.net/npm"
get() {  # $1 = الحزمة   $2 = اسم الملف في الحزمة   $3 = الاسم عندنا
  curl -fsSL --proto '=https' --tlsv1.2 "$BASE/$1/files/$2" -o "$3.tmp"
  # نتأكدو إن الملف فعلاً خط woff2 (يبدأ بـ wOF2) قبل ما نعتمدوه
  if [[ "$(head -c 4 "$3.tmp")" != "wOF2" ]]; then rm -f "$3.tmp"; echo "الملف $2 مش خط سليم"; exit 1; fi
  mv "$3.tmp" "$3"; chmod 644 "$3"; echo "✓ $3"
}

get "@fontsource/el-messiri@5"           el-messiri-arabic-700-normal.woff2           ElMessiri-arabic-700.woff2
get "@fontsource/el-messiri@5"           el-messiri-latin-700-normal.woff2            ElMessiri-latin-700.woff2
get "@fontsource/ibm-plex-sans-arabic@5" ibm-plex-sans-arabic-arabic-400-normal.woff2 Plex-arabic-400.woff2
get "@fontsource/ibm-plex-sans-arabic@5" ibm-plex-sans-arabic-latin-400-normal.woff2  Plex-latin-400.woff2
get "@fontsource/ibm-plex-sans-arabic@5" ibm-plex-sans-arabic-arabic-600-normal.woff2 Plex-arabic-600.woff2
get "@fontsource/ibm-plex-sans-arabic@5" ibm-plex-sans-arabic-latin-600-normal.woff2  Plex-latin-600.woff2
echo "تمام. عاود بناء الموقع: python3 -m manzumati.build"
