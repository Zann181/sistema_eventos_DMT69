(function () {
  function sanitizeValue(value, decimals) {
    let clean = String(value || "").trim().replace(/\s+/g, "");
    const dotCount = (clean.match(/\./g) || []).length;
    const commaCount = (clean.match(/,/g) || []).length;

    if (commaCount > 0) {
      clean = clean.replace(/\./g, "");
      clean = clean.replace(/,/g, ".");
    } else if (dotCount > 1) {
      clean = clean.replace(/\./g, "");
    } else if (dotCount === 1) {
      const [integerPart = "", decimalPart = ""] = clean.split(".");
      if (decimals === 0 && decimalPart.length > 0 && decimalPart.length <= 2) {
        clean = integerPart;
      } else if (decimals > 0 && decimalPart.length > 0 && decimalPart.length <= decimals) {
        clean = `${integerPart}.${decimalPart}`;
      } else {
        clean = `${integerPart}${decimalPart}`;
      }
    }

    clean = clean.replace(/[^\d.]/g, "");

    const firstDot = clean.indexOf(".");
    if (firstDot !== -1) {
      clean = clean.slice(0, firstDot + 1) + clean.slice(firstDot + 1).replace(/\./g, "");
    }

    if (decimals === 0) {
      return clean.split(".")[0];
    }

    const [integerPart = "", decimalPart = ""] = clean.split(".");
    return decimalPart ? `${integerPart}.${decimalPart.slice(0, decimals)}` : integerPart;
  }

  function formatThousands(value, decimals) {
    if (!value) {
      return "";
    }

    const normalized = sanitizeValue(value, decimals);
    if (!normalized) {
      return "";
    }

    const [integerPart = "", decimalPart = ""] = normalized.split(".");
    const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (decimals === 0 || !decimalPart) {
      return grouped;
    }
    return `${grouped},${decimalPart}`;
  }

  function normalizeForSubmit(value, decimals) {
    const normalized = sanitizeValue(value, decimals);
    return normalized || "";
  }

  function formatDisplayNumbers() {
    const formatter = new Intl.NumberFormat("es-CO");
    document.querySelectorAll("[data-number]").forEach((element) => {
      if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
        return;
      }
      const raw = element.getAttribute("data-number");
      if (raw === null || raw === "") {
        return;
      }
      const normalized = sanitizeValue(String(raw), 2);
      const value = Number(normalized);
      if (!Number.isFinite(value)) {
        return;
      }
      const formatted = formatter.format(value);
      element.textContent = element.dataset.format === "currency" ? `$ ${formatted}` : formatted;
    });
  }

  function bindFormattedInputs() {
    const inputs = document.querySelectorAll("input[data-thousands='true']");
    inputs.forEach((input) => {
      const decimals = Number.parseInt(input.dataset.decimals || "0", 10);
      if (!Number.isFinite(decimals)) {
        return;
      }

      const applyFormat = () => {
        input.value = formatThousands(input.value, decimals);
      };

      input.addEventListener("input", applyFormat);
      input.addEventListener("blur", applyFormat);

      if (input.value) {
        applyFormat();
      }

      const form = input.form;
      if (form && !form.dataset.thousandsBound) {
        form.addEventListener("submit", () => {
          form.querySelectorAll("input[data-thousands='true']").forEach((field) => {
            const fieldDecimals = Number.parseInt(field.dataset.decimals || "0", 10);
            field.value = normalizeForSubmit(field.value, fieldDecimals);
          });
        });
        form.dataset.thousandsBound = "true";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    formatDisplayNumbers();
    bindFormattedInputs();
  });

  window.NumberFormatting = {
    formatDisplayNumbers,
    bindFormattedInputs,
    formatThousands,
    normalizeForSubmit,
  };
})();
