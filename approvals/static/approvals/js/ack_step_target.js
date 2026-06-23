"use strict";

// Маршруты ознакомления: в зависимости от выбора «Кому» (target_type)
// в строке инлайна показываем только нужное поле:
//   role       → поле «Роль»
//   department → поле «Отдел»
//   all/heads  → оба поля скрыты (адресаты вычисляются автоматически)
(function () {
    function toggle(field, show) {
        if (!field) {
            return;
        }
        var container =
            field.closest(".form-row") ||
            field.closest("td") ||
            field.closest(".related-widget-wrapper") ||
            field;
        container.style.display = show ? "" : "none";
    }

    function updateRow(targetSelect) {
        var row =
            targetSelect.closest(".inline-related") || targetSelect.closest("tr");
        if (!row) {
            return;
        }
        var roleField = row.querySelector('select[name$="-department"]');
        var orgField = row.querySelector('select[name$="-org_department"]');
        var value = targetSelect.value;
        toggle(roleField, value === "role");
        toggle(orgField, value === "department");
    }

    function bind(targetSelect) {
        if (!targetSelect || targetSelect.dataset.ackBound === "1") {
            return;
        }
        if (targetSelect.name.indexOf("__prefix__") !== -1) {
            return;
        }
        targetSelect.dataset.ackBound = "1";
        targetSelect.addEventListener("change", function () {
            updateRow(targetSelect);
        });
        updateRow(targetSelect);
    }

    function bindAll(root) {
        (root || document)
            .querySelectorAll('select[name$="-target_type"]')
            .forEach(bind);
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindAll(document);
    });

    document.addEventListener("formset:added", function (event) {
        var row = event.target;
        if (row && row.querySelector) {
            bindAll(row);
        }
    });
})();
