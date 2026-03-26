/**
 * Зависимый select «Категория» от «Раздел спецификации».
 * Данные — из элемента #rkd-category-by-section (json_script в шаблоне админки).
 */
(function () {
  "use strict";

  function categoryMap() {
    var el = document.getElementById("rkd-category-by-section");
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(String(el.textContent).trim());
    } catch (e) {
      return {};
    }
  }

  function rebuild(sectionSelect) {
    var map = categoryMap();
    var key = sectionSelect.value || "";
    var codes = map[key] || [];
    var catName = sectionSelect.name.replace(/specification_section$/, "category");
    var root = sectionSelect.form || document;
    var cat = root.querySelector("[name=" + JSON.stringify(catName) + "]");
    if (!cat || cat.tagName !== "SELECT") return;

    var prev = cat.value;
    cat.innerHTML = "";
    var rows = [["", "---------"]];
    codes.forEach(function (c) {
      rows.push([c, c]);
    });
    rows.forEach(function (pair) {
      var o = document.createElement("option");
      o.value = pair[0];
      o.textContent = pair[1];
      cat.appendChild(o);
    });
    if (
      prev &&
      Array.prototype.some.call(cat.options, function (opt) {
        return opt.value === prev;
      })
    ) {
      cat.value = prev;
    } else {
      cat.value = "";
    }
  }

  function syncAll() {
    document
      .querySelectorAll(
        'select[name$="-specification_section"], select[name="specification_section"]'
      )
      .forEach(function (sel) {
        rebuild(sel);
      });
  }

  document.addEventListener("change", function (e) {
    var t = e.target;
    if (!t || !t.name || t.name.indexOf("specification_section") === -1) return;
    rebuild(t);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncAll);
  } else {
    syncAll();
  }

  document.addEventListener("formset:added", function () {
    setTimeout(syncAll, 0);
  });
})();
