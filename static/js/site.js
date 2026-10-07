/* منظومتي: البحث والفلترة داخل الصفحة.
 * قواعد أمان: ما نحطوش HTML من كود الجافاسكربت، ولا ننفذو نصوص ككود، ولا مكتبات خارجية.
 * كلام الزائر (اللي يكتبه في البحث) ما يتحطش في الصفحة أبداً، نقارنوه بس.
 */
(function () {
  "use strict";

  // توحيد الكتابة العربية باش البحث يلقى الكلمة مهما كانت مكتوبة:
  // أ/إ/آ ← ا، ة ← ه، ى ← ي، ؤ ← و، ئ ← ي، الأرقام العربية ← إنجليزية، وحذف التشكيل والتطويل
  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[\u064B-\u0652\u0640]/g, "")
      .replace(/[أإآٱ]/g, "ا")
      .replace(/ة/g, "ه")
      .replace(/ى/g, "ي")
      .replace(/ؤ/g, "و")
      .replace(/ئ/g, "ي")
      .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
      .replace(/[^\u0621-\u064Aa-z0-9 ]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  // نشيلو "ال" و "وال" من أول الكلمة: "المرتب" و "مرتب" و "والمرتب" يلقو نفس النتيجة
  function stem(w) {
    if (w.length > 4 && w.indexOf("وال") === 0) return w.slice(3);
    if (w.length > 3 && w.indexOf("ال") === 0) return w.slice(2);
    return w;
  }

  function words(s) {
    return norm(s).split(" ").filter(Boolean).map(stem);
  }

  var list = document.querySelector("[data-list]");
  if (!list) return;
  var items = Array.prototype.slice.call(list.querySelectorAll("li"));
  var empty = document.querySelector("[data-empty]");
  var input = document.getElementById("q");
  var filters = document.querySelector("[data-filters]");
  var current = "all";

  items.forEach(function (li) { li._s = " " + words(li.getAttribute("data-search")).join(" "); });

  function apply() {
    var q = input ? words(String(input.value).slice(0, 60)) : [];
    var shown = 0;
    items.forEach(function (li) {
      // كل كلمة من البحث لازم تكون بداية كلمة في بيانات المنظومة ("مرت" تلقى "مرتب")
      var okWords = q.every(function (w) { return li._s.indexOf(" " + w) !== -1; });
      var st = li.getAttribute("data-state");
      var okState = current === "all" || (current === "up" ? st === "up" : st === "down");
      var show = okWords && okState;
      li.hidden = !show;
      if (show) shown++;
    });
    if (empty) empty.hidden = shown !== 0;
  }

  if (input) {
    var q = new URLSearchParams(window.location.search).get("q");
    if (q) input.value = q.slice(0, 60);
    input.addEventListener("input", apply);
    var form = input.form;
    if (form) form.addEventListener("submit", function (e) {
      e.preventDefault();
      apply();
    });
  }

  if (filters) {
    filters.hidden = false;  // الأزرار تظهر بس لو الجافاسكربت شغال
    var chips = Array.prototype.slice.call(filters.querySelectorAll("[data-filter]"));
    chips.forEach(function (b) {
      b.addEventListener("click", function () {
        current = b.getAttribute("data-filter");
        chips.forEach(function (c) { c.setAttribute("aria-pressed", c === b ? "true" : "false"); });
        apply();
      });
    });
  }

  apply();
})();
