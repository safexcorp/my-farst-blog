/**
 * Зависимый select «Категория» от «Раздел спецификации».
 * Данные — из элемента #rkd-category-by-section (json_script в шаблоне админки).
 */
(function () {
  "use strict";

  var POSITION_EDITABLE_SECTIONS = new Set([
    "assembly_units",
    "parts",
    "standard_products",
    "other_products",
    "materials",
  ]);

  function sectionAllowsPosition(sectionCode) {
    return POSITION_EDITABLE_SECTIONS.has(sectionCode || "");
  }

  function syncPosition(sectionSelect) {
    var sectionCode = sectionSelect.value || "";
    var posName = sectionSelect.name.replace(/specification_section$/, "position");
    var root = sectionSelect.form || document;
    var pos = root.querySelector("[name=" + JSON.stringify(posName) + "]");
    if (!pos || (pos.tagName !== "INPUT" && pos.tagName !== "TEXTAREA")) return;

    if (sectionAllowsPosition(sectionCode)) {
      pos.disabled = false;
      if (pos.value === "-") pos.value = "";
      return;
    }

    pos.value = "-";
    pos.disabled = true;
  }

  function syncOneField(fieldName, allowed) {
    var field = document.querySelector("[name=" + JSON.stringify(fieldName) + "]");
    if (!field || (field.tagName !== "INPUT" && field.tagName !== "TEXTAREA")) return;
    if (allowed) {
      field.disabled = false;
      if (field.value === "-") field.value = "";
    } else {
      field.value = "-";
      field.disabled = true;
    }
  }

  function syncQuantityWeight(sectionSelect) {
    var sectionCode = sectionSelect.value || "";
    var allowed = POSITION_EDITABLE_SECTIONS.has(sectionCode || "");
    var base = sectionSelect.name.replace(/specification_section$/, "");
    syncOneField(base + "quantity", allowed);
    syncOneField(base + "weight", allowed);
  }

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

    if (cat && cat.tagName === "SELECT") {
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

    syncPosition(sectionSelect);
    syncQuantityWeight(sectionSelect);
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
