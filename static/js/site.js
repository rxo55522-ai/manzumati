/* منظومتي: البحث والفلترة داخل الصفحة.
 * قواعد أمان: ما نحطوش HTML من كود الجافاسكربت، ولا ننفذو نصوص ككود، ولا مكتبات خارجية.
 * كلام الزائر (اللي يكتبه في البحث) ما يتحطش في الصفحة أبداً، نقارنوه بس.
 */
(function () {
  "use strict";

  // توحيد الكتابة العربية: أ/إ/آ ← ا، ة ← ه، ى ← ي، وحذف التشكيل والتطويل
  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[ً-ْـ]/g, "")
      .replace(/[أإآ]/g, "ا")
      .replace(/ة/g, "ه")
      .replace(/ى/g, "ي")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 60);
  }

  var list = document.querySelector("[data-list]");
  if (!list) return;
  var items = Array.prototype.slice.call(list.querySelectorAll("li"));
  var empty = document.querySelector("[data-empty]");
  var input = document.getElementById("q");
  var filters = document.querySelector("[data-filters]");
  var current = "all";

  items.forEach(function (li) { li._s = norm(li.getAttribute("data-search")); });

  function apply() {
    var words = input ? norm(input.value).split(" ").filter(Boolean) : [];
    var shown = 0;
    items.forEach(function (li) {
      var okWords = words.every(function (w) { return li._s.indexOf(w) !== -1; });
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
