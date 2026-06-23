"use strict";

// Автонумерация поля "Порядок" / "Очередь замещения" в инлайнах:
// при добавлении новой строки значение становится (максимум + 1),
// а не дефолтной единицей.
(function () {
    function fieldSuffix(name) {
        if (name.endsWith("-order")) {
            return "-order";
        }
        return null;
    }

    function renumber(newInput) {
        var suffix = fieldSuffix(newInput.name);
        if (!suffix) {
            return;
        }
        // Префикс формсета: всё до "-<index>-order".
        var prefix = newInput.name.replace(/-\d+-order$/, "");
        var selector =
            'input[name^="' + prefix + '-"][name$="' + suffix + '"]';
        var max = 0;
        document.querySelectorAll(selector).forEach(function (inp) {
            if (inp === newInput) {
                return;
            }
            if (inp.name.indexOf("__prefix__") !== -1) {
                return;
            }
            var value = parseInt(inp.value, 10);
            if (!isNaN(value) && value > max) {
                max = value;
            }
        });
        newInput.value = max + 1;
    }

    document.addEventListener("formset:added", function (event) {
        var row = event.target;
        if (!row || !row.querySelector) {
            return;
        }
        var orderInput = row.querySelector('input[name$="-order"]');
        if (orderInput) {
            renumber(orderInput);
        }
    });
})();
