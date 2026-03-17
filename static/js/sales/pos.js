const saleForm = document.getElementById("sale-form");
const salesShell = document.querySelector("[data-sales-shell]");

const formatCurrency = (value) =>
  new Intl.NumberFormat("es-CO", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));

const parseNumber = (value) => {
  if (!value) return 0;
  const normalized = String(value).replace(/\./g, "").replace(",", ".");
  return Number.parseFloat(normalized) || 0;
};

const bindPaymentBreakdown = () => {
  document.querySelectorAll("[data-payment-breakdown]").forEach((wrapper) => {
    const rows = Array.from(wrapper.querySelectorAll("[data-payment-row]"));
    const addButton = wrapper.querySelector("[data-add-payment-row]");
    const removeButtons = Array.from(wrapper.querySelectorAll("[data-remove-payment-row]"));

    const updateVisibleRows = () => {
      rows.forEach((row) => {
        const methodSelect = row.querySelector(".payment-method-select");
        const transferProofRow = row.querySelector("[data-transfer-proof-row]");
        if (methodSelect && transferProofRow) {
          transferProofRow.classList.toggle("d-none", methodSelect.value !== "transferencia");
        }
      });
    };

    const syncAddButton = () => {
      if (!addButton) return;
      addButton.disabled = !rows.some((row) => row.classList.contains("d-none"));
    };

    const clearRow = (row) => {
      row.querySelectorAll("input").forEach((input) => {
        if (input.type === "file") {
          input.value = "";
        } else {
          input.value = "";
        }
      });
      row.querySelectorAll("select").forEach((select) => {
        select.value = "";
      });
      row.querySelectorAll("[data-payment-change-output]").forEach((output) => {
        output.textContent = "$ 0";
      });
    };

    rows.forEach((row) => {
      row.querySelector(".payment-method-select")?.addEventListener("change", updateVisibleRows);
    });

    addButton?.addEventListener("click", () => {
      const hiddenRow = rows.find((row) => row.classList.contains("d-none"));
      if (hiddenRow) {
        hiddenRow.classList.remove("d-none");
        const methodSelect = hiddenRow.querySelector(".payment-method-select");
        if (methodSelect && !methodSelect.value) {
          methodSelect.value = "efectivo";
        }
      }
      updateVisibleRows();
      syncAddButton();
    });

    removeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest("[data-payment-row]");
        if (!row) return;
        const visibleRows = rows.filter((item) => !item.classList.contains("d-none"));
        clearRow(row);
        if (visibleRows.length > 1) {
          row.classList.add("d-none");
        }
        updateVisibleRows();
        syncAddButton();
        row.querySelector('input[name^="sale_payment_amount_"]')?.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });

    updateVisibleRows();
    syncAddButton();
  });
};

const bindSaleCalculator = () => {
  if (!saleForm) return;

  const productSelect = saleForm.querySelector("[data-sale-product-select]");
  const quantityInput = saleForm.querySelector("#id_quantity");
  const cartInput = saleForm.querySelector("[data-sale-cart-input]");
  const productCards = Array.from(document.querySelectorAll("[data-product-card]"));
  const previewTotalClone = saleForm.querySelector("[data-sale-total-clone]");
  const saleLines = saleForm.querySelector("[data-sale-lines]");
  const includedCheckbox = saleForm.querySelector("#id_use_included_balance");
  const paymentShell = saleForm.querySelector("[data-sale-payment-shell]");
  const paymentInputs = () =>
    Array.from(saleForm.querySelectorAll('input[name^="sale_payment_amount_"]')).filter(
      (input) => !input.closest("[data-payment-row]")?.classList.contains("d-none")
    );
  const paymentRows = () => Array.from(saleForm.querySelectorAll("[data-payment-row]"));
  const productOptions = Array.from(productSelect?.options || []).reduce((accumulator, option) => {
    if (option.value) {
      accumulator[option.value] = {
        id: option.value,
        name: option.dataset.name || option.textContent || "Producto",
        image: option.dataset.image || "",
        price: parseNumber(option.dataset.price || 0),
      };
    }
    return accumulator;
  }, {});
  let cart = [];

  const getCurrentTotal = () =>
    cart.reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 0), 0);

  const updateChangeOutputs = () => {
    let coveredBefore = 0;
    const total = getCurrentTotal();

    paymentRows().forEach((row) => {
      if (row.classList.contains("d-none")) return;
      const amountInput = row.querySelector('input[name^="sale_payment_amount_"]');
      const changeOutput = row.querySelector("[data-payment-change-output]");
      const amount = parseNumber(amountInput?.value || 0);
      const pendingBefore = Math.max(total - coveredBefore, 0);
      const change = Math.max(amount - pendingBefore, 0);
      if (changeOutput) {
        changeOutput.textContent = `$ ${formatCurrency(change)}`;
      }
      coveredBefore += amount;
    });
  };

  const syncSelectedCard = () => {
    productCards.forEach((card) => {
      const isSelected = cart.some((item) => item.id === card.dataset.productId);
      card.classList.toggle("is-selected", isSelected);
    });
  };

  const syncHiddenFields = () => {
    if (cartInput) {
      cartInput.value = JSON.stringify(cart.map((item) => ({ event_product_id: item.id, quantity: item.quantity })));
    }
    if (productSelect) {
      productSelect.value = cart[0]?.id || "";
    }
    if (quantityInput) {
      quantityInput.value = String(cart[0]?.quantity || 1);
    }
  };

  const renderLines = () => {
    if (!saleLines) return;
    if (!cart.length) {
      saleLines.innerHTML = `
        <div class="sales-invoice-empty">
          <i class="fas fa-receipt"></i>
          <strong>La factura esta vacia</strong>
          <span>Haz clic en un producto para agregarlo al pedido.</span>
        </div>
      `;
      return;
    }

    saleLines.innerHTML = cart
      .map(
        (item) => `
          <div class="sales-invoice-line" data-sale-line>
            <div class="sales-invoice-line-main">
              <div class="sales-invoice-line-media">
                ${
                  item.image
                    ? `<img src="${item.image}" alt="${item.name}">`
                    : '<i class="fas fa-martini-glass-citrus"></i>'
                }
              </div>
              <div class="sales-invoice-line-copy">
                <span class="eyebrow">Producto</span>
                <strong>${item.name}</strong>
                <div class="sales-invoice-line-meta">
                  <span>Unitario</span>
                  <strong>$ ${formatCurrency(item.price)}</strong>
                </div>
              </div>
            </div>
            <div class="sales-invoice-line-quantity-block">
              <span class="eyebrow">Cantidad</span>
              <div class="sales-invoice-quantity">
                <button type="button" class="sales-product-step" data-cart-step="-1" data-cart-product-id="${item.id}" aria-label="Restar cantidad">
                  <i class="fas fa-minus"></i>
                </button>
                <strong>${item.quantity}</strong>
                <button type="button" class="sales-product-step" data-cart-step="1" data-cart-product-id="${item.id}" aria-label="Sumar cantidad">
                  <i class="fas fa-plus"></i>
                </button>
              </div>
            </div>
            <div class="sales-invoice-line-aside">
              <div class="sales-invoice-line-total">
                <span>Total</span>
                <strong>$ ${formatCurrency(item.price * item.quantity)}</strong>
              </div>
              <button type="button" class="sales-invoice-remove" data-cart-remove="${item.id}" aria-label="Eliminar producto">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
        `
      )
      .join("");
  };

  const updateTotals = () => {
    const total = getCurrentTotal();
    if (previewTotalClone) {
      previewTotalClone.textContent = `$ ${formatCurrency(total)}`;
    }
    if (paymentShell) {
      paymentShell.classList.toggle("d-none", Boolean(includedCheckbox?.checked));
    }
    renderLines();
    syncHiddenFields();
    syncSelectedCard();
    updateChangeOutputs();
  };

  const addProduct = (productId) => {
    const product = productOptions[productId];
    if (!product) return;
    const existingItem = cart.find((item) => item.id === productId);
    if (existingItem) {
      existingItem.quantity += 1;
    } else {
      cart.push({ ...product, quantity: 1 });
    }
    updateTotals();
  };

  const changeQuantity = (productId, step) => {
    const item = cart.find((entry) => entry.id === productId);
    if (!item) return;
    item.quantity = Math.max(item.quantity + step, 0);
    cart = cart.filter((entry) => entry.quantity > 0);
    updateTotals();
  };

  const removeProduct = (productId) => {
    cart = cart.filter((entry) => entry.id !== productId);
    updateTotals();
  };

  productCards.forEach((card) => {
    const selectCard = () => addProduct(card.dataset.productId);

    card.addEventListener("click", selectCard);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectCard();
      }
    });

  });

  saleLines?.addEventListener("click", (event) => {
    const stepButton = event.target.closest("[data-cart-step]");
    if (stepButton) {
      changeQuantity(stepButton.dataset.cartProductId, parseInt(stepButton.dataset.cartStep || "0", 10));
      return;
    }
    const removeButton = event.target.closest("[data-cart-remove]");
    if (removeButton) {
      removeProduct(removeButton.dataset.cartRemove);
    }
  });

  includedCheckbox?.addEventListener("change", updateTotals);

  paymentRows().forEach((row) => {
    row.querySelector(".payment-method-select")?.addEventListener("change", updateChangeOutputs);
    row.querySelector('input[name^="sale_payment_amount_"]')?.addEventListener("input", updateChangeOutputs);
  });

  saleForm.querySelectorAll("[data-quick-payment-amount]").forEach((button) => {
    button.addEventListener("click", () => {
      const amount = parseNumber(button.dataset.quickPaymentAmount);
      const firstInput = paymentInputs()[0];
      if (firstInput) {
        const currentAmount = parseNumber(firstInput.value || 0);
        firstInput.value = formatCurrency(currentAmount + amount);
        firstInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  });

  saleForm.querySelector("[data-quick-payment-total]")?.addEventListener("click", () => {
    const firstInput = paymentInputs()[0];
    if (firstInput) {
      firstInput.value = formatCurrency(getCurrentTotal());
      firstInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  saleForm.querySelector("[data-quick-payment-clear]")?.addEventListener("click", () => {
    paymentInputs().forEach((input) => {
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    updateChangeOutputs();
  });

  if (quantityInput && (!quantityInput.value || parseInt(quantityInput.value, 10) < 1)) {
    quantityInput.value = "1";
  }
  updateTotals();
  updateChangeOutputs();
};

const bindSaleSubmit = () => {
  if (!saleForm) return;

  saleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = document.getElementById("sale-result");
    const formData = new FormData(saleForm);

    const response = await fetch(saleForm.dataset.endpoint, {
      method: "POST",
      body: formData,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json();
    result.innerHTML = `<div class="alert alert-${payload.success ? "success" : "warning"}">${payload.message}</div>`;
    if (payload.success) {
      window.location.reload();
    }
  });
};

const bindActionModal = (action, modalId) => {
  const actionValue = salesShell?.dataset.initialAction || new URLSearchParams(window.location.search).get("action");
  const modalElement = document.getElementById(modalId);
  if (!modalElement) {
    if (actionValue === action) {
      const url = new URL(window.location.href);
      if (url.searchParams.get("action") === action) {
        url.searchParams.delete("action");
        window.history.replaceState({}, "", url);
      }
    }
    return;
  }
  if (actionValue === action) {
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
  }
  modalElement.addEventListener("hidden.bs.modal", () => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("action") === action) {
      url.searchParams.delete("action");
      window.history.replaceState({}, "", url);
    }
  });
};

const bindProductEditModal = () => {
  const modalElement = document.getElementById("salesProductEditModal");
  const form = modalElement?.querySelector("[data-product-edit-form]");
  if (!modalElement || !form) return;

  const nameInput = form.querySelector("#sales-product-edit-name");
  const descriptionInput = form.querySelector("#sales-product-edit-description");
  const imageInput = form.querySelector("#sales-product-edit-image");
  const activeInput = form.querySelector("#sales-product-edit-active");
  const previewShell = form.querySelector("[data-product-edit-preview-shell]");
  const previewImage = form.querySelector("[data-product-edit-preview]");

  document.querySelectorAll("[data-edit-product-button]").forEach((button) => {
    button.addEventListener("click", () => {
      form.action = button.dataset.productUpdateUrl || "";
      if (nameInput) {
        nameInput.value = button.dataset.productName || "";
      }
      if (descriptionInput) {
        descriptionInput.value = button.dataset.productDescription || "";
      }
      if (activeInput) {
        activeInput.checked = button.dataset.productActive === "true";
      }
      if (imageInput) {
        imageInput.value = "";
      }
      if (previewShell && previewImage) {
        const imageUrl = button.dataset.productImage || "";
        previewShell.classList.toggle("d-none", !imageUrl);
        previewImage.src = imageUrl;
      }
      bootstrap.Modal.getOrCreateInstance(modalElement).show();
    });
  });
};

if (salesShell) {
  bindPaymentBreakdown();
  bindSaleCalculator();
  bindSaleSubmit();
  bindProductEditModal();
  bindActionModal("productos", "salesProductModal");
  bindActionModal("evento-productos", "salesEventProductsModal");
  bindActionModal("gastos", "salesExpenseModal");
  bindActionModal("vaciar-caja", "salesCashDropModal");
}
