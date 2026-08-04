/*
 * Каскад «Разработка (модификация) → Изделие к отгрузке» для протоколов
 * ПСИ ИБП СПМ и ПСИ ПАК СПМ (лист замечаний 21.07.2026, п. 6 / п. 5).
 *
 * При выборе разработки (#id_post) поле «Изделие к отгрузке» (#id_shipment)
 * подгружает только те изделия, которые относятся к выбранной разработке.
 * URL источника данных берётся из атрибута data-shipments-url поля #id_post,
 * который проставляет админка (get_form -> reverse(...)).
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    ready(function () {
        var postSelect = document.getElementById("id_post");
        var shipmentSelect = document.getElementById("id_shipment");

        if (!postSelect || !shipmentSelect) {
            return;
        }

        var url = postSelect.getAttribute("data-shipments-url");
        if (!url) {
            return;
        }

        function resetShipmentOptions() {
            shipmentSelect.innerHTML = "";
            var placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "---------";
            shipmentSelect.appendChild(placeholder);
        }

        postSelect.addEventListener("change", function () {
            var postId = postSelect.value;
            resetShipmentOptions();

            if (!postId) {
                return;
            }

            fetch(url + "?post_id=" + encodeURIComponent(postId), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin"
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    var results = (data && data.results) || [];
                    results.forEach(function (item) {
                        var option = document.createElement("option");
                        option.value = item.id;
                        option.textContent = item.text;
                        // Синим подсвечиваем изделия без Протокола ПСИ.
                        if (item.no_psi) {
                            option.style.color = "#1a56db";
                            option.setAttribute("data-no-psi", "1");
                        }
                        shipmentSelect.appendChild(option);
                    });
                })
                .catch(function () {
                    /* Тихо игнорируем сбой сети: список остаётся пустым. */
                });
        });
    });
})();
