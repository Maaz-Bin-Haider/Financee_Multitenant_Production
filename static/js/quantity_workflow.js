(function () {
  "use strict";

  function notify(kind, message) {
    if (window.Alerts && typeof window.Alerts[kind] === "function") {
      window.Alerts[kind](message);
    } else {
      window.alert(message);
    }
  }

  async function run(button, operation) {
    if (!button || button.dataset.quantityBusy === "true") return;
    button.dataset.quantityBusy = "true";
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    const original = button.innerHTML;
    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing…';
    try {
      return await operation();
    } finally {
      button.innerHTML = original;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      delete button.dataset.quantityBusy;
    }
  }

  function initialize() {
    document.querySelectorAll("button:not([type])").forEach((button) => {
      button.type = "button";
    });
    document.querySelectorAll("input[type='date']").forEach((input) => {
      if (!input.value && !input.disabled) {
        input.value = new Date().toISOString().slice(0, 10);
      }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        const save = document.getElementById("save");
        if (save && !save.disabled) {
          event.preventDefault();
          save.click();
        }
      }
    });
  }

  window.QuantityUI = { notify, run, initialize };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
})();
