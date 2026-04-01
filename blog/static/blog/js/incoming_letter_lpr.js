(function () {
  function apiUrlWithQuery(customerId) {
    var base =
      typeof window.INCOMING_LETTER_LPR_URL === "string" &&
      window.INCOMING_LETTER_LPR_URL.length
        ? window.INCOMING_LETTER_LPR_URL.replace(/\/?$/, "")
        : "/crm/api/decision-makers-by-customer";
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    return base + sep + "customer_id=" + encodeURIComponent(customerId);
  }

  function escapeHtml(text) {
    var d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }

  function fillSignatureSelect(selectEl, results, selectedId) {
    var html = '<option value="">---------</option>';
    for (var i = 0; i < results.length; i++) {
      var row = results[i];
      var id = String(row.id);
      var sel =
        selectedId != null && String(selectedId) === id ? " selected" : "";
      html +=
        '<option value="' +
        id +
        '"' +
        sel +
        ">" +
        escapeHtml(row.text) +
        "</option>";
    }
    selectEl.innerHTML = html;
  }

  function loadLprForCustomer(customerId, signatureSelect, keepSelectedId) {
    if (!signatureSelect) {
      return;
    }
    if (!customerId) {
      fillSignatureSelect(signatureSelect, [], null);
      return;
    }
    fetch(apiUrlWithQuery(customerId), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) {
        if (!r.ok) {
          return { results: [] };
        }
        return r.json();
      })
      .then(function (data) {
        var results = data.results || [];
        var preserve = null;
        if (
          keepSelectedId != null &&
          results.some(function (x) {
            return String(x.id) === String(keepSelectedId);
          })
        ) {
          preserve = keepSelectedId;
        }
        fillSignatureSelect(signatureSelect, results, preserve);
      })
      .catch(function () {
        fillSignatureSelect(signatureSelect, [], null);
      });
  }

  function bindSenderChange(senderEl, signatureSelect) {
    function onSenderChange() {
      var v = senderEl.value;
      loadLprForCustomer(v, signatureSelect, null);
    }
    senderEl.addEventListener("change", onSenderChange);
    if (typeof django !== "undefined" && django.jQuery) {
      django.jQuery(senderEl).on("select2:select select2:clear", onSenderChange);
    }
  }

  function replyToSenderApiBase() {
    if (
      typeof window.REPLY_TO_INCOMING_SENDER_URL === "string" &&
      window.REPLY_TO_INCOMING_SENDER_URL.length
    ) {
      return window.REPLY_TO_INCOMING_SENDER_URL.replace(/\/?$/, "");
    }
    return "/crm/api/incoming-letter-sender/";
  }

  function setRecipientFromIncomingLetter(incomingLetterId) {
    var recipientEl = document.getElementById("id_recipient");
    var personEl = document.getElementById("id_person_recipient");
    if (!recipientEl || !incomingLetterId) {
      return;
    }
    var url =
      replyToSenderApiBase() +
      (replyToSenderApiBase().indexOf("?") >= 0 ? "&" : "?") +
      "incoming_letter_id=" +
      encodeURIComponent(incomingLetterId);
    fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) {
        if (!r.ok) {
          return {};
        }
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.sender_id) {
          return;
        }
        var sid = String(data.sender_id);
        var label = data.sender_label || sid;
        if (typeof django !== "undefined" && django.jQuery) {
          var $r = django.jQuery(recipientEl);
          $r.find("option").filter(function () {
            return String(this.value) === sid;
          }).remove();
          var opt = new Option(label, sid, true, true);
          $r.append(opt).val(sid).trigger("change");
        } else {
          var optEl = document.createElement("option");
          optEl.value = sid;
          optEl.textContent = label;
          optEl.selected = true;
          recipientEl.appendChild(optEl);
          recipientEl.value = sid;
          recipientEl.dispatchEvent(new Event("change", { bubbles: true }));
        }
        /* Select2 отдаёт change до того, как val() виден в обработчике — грузим ЛПР явно */
        if (personEl) {
          loadLprForCustomer(sid, personEl, null);
        }
      })
      .catch(function () {});
  }

  function bindReplyToToRecipient() {
    var replyTo = document.getElementById("id_reply_to");
    var recipient = document.getElementById("id_recipient");
    if (!replyTo || !recipient) {
      return;
    }
    function onReplyToChange() {
      var v = replyTo.value;
      if (!v) {
        return;
      }
      setRecipientFromIncomingLetter(v);
    }
    replyTo.addEventListener("change", onReplyToChange);
    if (typeof django !== "undefined" && django.jQuery) {
      django.jQuery(replyTo).on("select2:select", onReplyToChange);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var sender = document.getElementById("id_sender");
    var sig = document.getElementById("id_sender_signature");
    if (sender && sig) {
      bindSenderChange(sender, sig);
    }
    var recipient = document.getElementById("id_recipient");
    var personRecipient = document.getElementById("id_person_recipient");
    if (recipient && personRecipient) {
      bindSenderChange(recipient, personRecipient);
    }
    bindReplyToToRecipient();
  });
})();
