(function () {
  const formatThousands = window.NumberFormatting?.formatThousands;

  const splitSelectors = (value) =>
    String(value || "")
      .split(",")
      .map((selector) => selector.trim())
      .filter(Boolean);

  const resolveInputs = (scope, selectors) => {
    const seen = new Set();
    return selectors.flatMap((selector) =>
      Array.from(scope.querySelectorAll(selector)).filter((input) => {
        if (!(input instanceof HTMLInputElement) && !(input instanceof HTMLTextAreaElement)) {
          return false;
        }
        if (seen.has(input)) {
          return false;
        }
        seen.add(input);
        return true;
      }),
    );
  };

  const dispatchUpdates = (input) => {
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const setFormattedValue = (input, rawValue) => {
    const decimals = Number.parseInt(input.dataset.decimals || "0", 10);
    input.value = formatThousands ? formatThousands(String(rawValue), Number.isFinite(decimals) ? decimals : 0) : String(rawValue);
    dispatchUpdates(input);
  };

  const clearValue = (input) => {
    input.value = "";
    dispatchUpdates(input);
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-quick-fill-group]").forEach((group) => {
      const scope = group.closest("form") || document;
      const fillSelectors = splitSelectors(group.dataset.quickFillTargets);
      const clearSelectors = splitSelectors(group.dataset.quickClearTargets || group.dataset.quickFillTargets);

      group.querySelectorAll("[data-quick-fill-amount]").forEach((button) => {
        button.addEventListener("click", () => {
          const amount = button.dataset.quickFillAmount || "";
          resolveInputs(scope, fillSelectors).forEach((input) => setFormattedValue(input, amount));
        });
      });

      group.querySelector("[data-quick-fill-clear]")?.addEventListener("click", () => {
        resolveInputs(scope, clearSelectors).forEach(clearValue);
      });
    });
  });
})();
