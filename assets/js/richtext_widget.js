(function () {
  "use strict";

  var FONT_WHITELIST = [
    "arial", "times-new-roman", "courier-new", "georgia", "verdana", "tahoma",
  ];

  function registerFonts() {
    if (window.__richTextFontsRegistered) return;
    var Font = Quill.import("formats/font");
    Font.whitelist = FONT_WHITELIST;
    Quill.register(Font, true);
    window.__richTextFontsRegistered = true;
  }

  function looksLikeHtml(value) {
    return /^\s*<[a-z][\s\S]*>/i.test(value || "");
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function plainTextToHtml(value) {
    var lines = (value || "").split(/\r\n|\r|\n/);
    return lines
      .map(function (line) {
        return line.trim() === "" ? "<p><br></p>" : "<p>" + escapeHtml(line) + "</p>";
      })
      .join("");
  }

  function initOne(textarea) {
    if (textarea.dataset.richtextInit) return;
    textarea.dataset.richtextInit = "1";
    textarea.style.display = "none";

    var wrapper = document.createElement("div");
    wrapper.className = "richtext-field";
    textarea.parentNode.insertBefore(wrapper, textarea);

    var container = document.createElement("div");
    wrapper.appendChild(container);

    var quill = new Quill(container, {
      theme: "snow",
      modules: {
        toolbar: [
          [{ font: FONT_WHITELIST }, { size: ["small", false, "large", "huge"] }],
          ["bold", "italic", "underline", "strike"],
          [{ list: "ordered" }, { list: "bullet" }],
          [{ indent: "-1" }, { indent: "+1" }],
          [{ align: [] }],
          ["clean"],
        ],
      },
    });

    var initial = textarea.value;
    if (looksLikeHtml(initial)) {
      quill.root.innerHTML = initial;
    } else {
      quill.root.innerHTML = plainTextToHtml(initial);
    }

    quill.root.setAttribute("spellcheck", "true");
    quill.root.setAttribute("lang", textarea.dataset.richtextLang || "ru");

    var form = textarea.closest("form");
    if (form) {
      form.addEventListener("submit", function () {
        textarea.value = quill.root.innerHTML;
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof Quill === "undefined") return;
    registerFonts();
    document.querySelectorAll("textarea[data-richtext]").forEach(initOne);
  });
})();
