(function () {
  const shell = document.querySelector(".entrada-shell");
  if (!shell) {
    return;
  }

  const config = {
    categoryPrices: JSON.parse(shell.dataset.categoryPrices || "{}"),
    listUrl: shell.dataset.listUrl,
    previewUrl: shell.dataset.previewUrl,
    confirmUrl: shell.dataset.confirmUrl,
    markUrl: shell.dataset.markUrl,
    deleteUrl: shell.dataset.deleteUrl,
    qrPattern: shell.dataset.qrPattern,
    username: shell.dataset.username || "",
    openModal: shell.dataset.openModal || "",
  };
  const CONTENT_TABS = new Set(["scanner", "lista", "crear"]);
  const MODAL_TABS = new Set(["categorias", "evento-dia", "gastos", "vaciar-caja"]);

  let html5QrCode = null;
  let isScanning = false;
  let verificationPayload = null;

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatNumbers() {
    if (window.NumberFormatting?.formatDisplayNumbers) {
      window.NumberFormatting.formatDisplayNumbers();
    }
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    return { response, payload };
  }

  async function loadList(page = 1) {
    const search = document.getElementById("filtro-buscar")?.value || "";
    const status = document.getElementById("filtro-estado")?.value || "";
    const items = document.getElementById("items-selector")?.value || "10";
    const params = new URLSearchParams();
    if (search) params.append("buscar", search);
    if (status) params.append("estado", status);
    if (items) params.append("items", items);
    params.append("page", page);

    const response = await fetch(`${config.listUrl}?${params.toString()}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const html = await response.text();
    document.getElementById("lista-asistentes").innerHTML = html;
    formatNumbers();
    bindListFooter();
  }

  function bindListFooter() {
    const selector = document.getElementById("items-selector");
    if (selector) {
      selector.addEventListener("change", () => loadList(1));
    }
  }

  function showMessage(containerId, kind, message) {
    const container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    container.innerHTML = `<div class="alert alert-${kind}">${message}</div>`;
  }

  function showInfoModal(title, content) {
    document.getElementById("info-modal-title").innerHTML = title;
    document.getElementById("info-modal-content").innerHTML = content;
    bootstrap.Modal.getOrCreateInstance(document.getElementById("infoModal")).show();
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatModalNumber(value, options = {}) {
    const raw = String(value ?? "").trim();
    if (!raw) {
      return options.fallback || "N/A";
    }

    const normalized = raw.replace(/\./g, "").replace(",", ".");
    const parsed = Number(normalized);
    if (!Number.isFinite(parsed)) {
      return escapeHtml(raw);
    }

    const formatter = new Intl.NumberFormat("es-CO", {
      minimumFractionDigits: 0,
      maximumFractionDigits: options.maximumFractionDigits ?? 2,
    });
    return formatter.format(parsed);
  }

  function buildVerificationHtml(attendee) {
    const now = new Date();
    const date = now.toLocaleDateString("es-CO");
    const time = now.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const infoItems = [
      ["Nombre", attendee.name],
      ["Cedula", attendee.cc],
      ["Telefono", attendee.phone || "N/A"],
      ["Correo", attendee.email || "N/A"],
      ["Categoria", attendee.category],
      ["Precio pagado", `$ ${formatModalNumber(attendee.paid_amount)}`],
      ["Balance", formatModalNumber(attendee.balance, { maximumFractionDigits: 0 })],
      ["Registro", attendee.created_at || "N/A"],
    ];

    const accessItems = [
      ["Fecha", date],
      ["Hora", time],
      ["Verificado por", config.username || "N/A"],
    ];

    return `
      <div class="verification-layout">
        <section class="verification-panel verification-panel--main">
          <div class="verification-panel-head">
            <span class="verification-kicker">Asistente</span>
            <h6>Datos del asistente</h6>
          </div>
          <div class="verification-grid">
            ${infoItems
              .map(
                ([label, value]) => `
                  <div class="verification-item">
                    <span class="verification-label">${escapeHtml(label)}</span>
                    <span class="verification-value">${escapeHtml(value)}</span>
                  </div>
                `
              )
              .join("")}
          </div>
        </section>
        <aside class="verification-panel verification-panel--side">
          <div class="verification-panel-head">
            <span class="verification-kicker">Control</span>
            <h6>Ingreso</h6>
          </div>
          <div class="verification-side-stack">
            ${accessItems
              .map(
                ([label, value]) => `
                  <div class="verification-stat">
                    <span class="verification-label">${escapeHtml(label)}</span>
                    <strong class="verification-stat-value">${escapeHtml(value)}</strong>
                  </div>
                `
              )
              .join("")}
          </div>
        </aside>
      </div>
      <div class="verification-note">
        <strong>Confirmar ingreso</strong>
        <span>Esta accion marcara al asistente como ingresado y cerrara la validacion actual.</span>
      </div>
    `;
  }

  async function onScanSuccess(decodedText) {
    if (!isScanning) {
      return;
    }
    isScanning = false;
    showMessage("scan-result", "info", "Verificando codigo QR...");

    const { payload } = await fetchJson(config.previewUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ codigo: decodedText }),
    });

    if (!payload.success) {
      showMessage("scan-result", "danger", payload.message);
      setTimeout(() => {
        if (!document.getElementById("stop-btn").hidden) {
          isScanning = true;
        }
      }, 2500);
      return;
    }

    verificationPayload = { codigo: decodedText, attendee: payload.attendee };
    document.getElementById("verification-content").innerHTML = buildVerificationHtml(payload.attendee);
    document.getElementById("scan-result").innerHTML = "";
    bootstrap.Modal.getOrCreateInstance(document.getElementById("verificationModal")).show();
  }

  async function startScanner() {
    if (!window.Html5Qrcode) {
      showMessage("scan-result", "danger", "No se pudo cargar el lector QR.");
      return;
    }

    if (!html5QrCode) {
      html5QrCode = new Html5Qrcode("reader");
    }

    try {
      await html5QrCode.start(
        { facingMode: "environment" },
        { fps: 12, qrbox: { width: 280, height: 280 } },
        onScanSuccess
      );
    } catch (error) {
      try {
        await html5QrCode.start(
          { facingMode: "user" },
          { fps: 12, qrbox: { width: 280, height: 280 } },
          onScanSuccess
        );
      } catch (fallbackError) {
        showMessage("scan-result", "danger", "No fue posible iniciar la camara.");
        return;
      }
    }

    isScanning = true;
    document.getElementById("start-btn").hidden = true;
    document.getElementById("stop-btn").hidden = false;
    showMessage("scan-result", "success", "Scanner activo. Posiciona el QR frente a la camara.");
  }

  async function stopScanner() {
    if (html5QrCode && isScanning) {
      await html5QrCode.stop();
    }
    isScanning = false;
    document.getElementById("start-btn").hidden = false;
    document.getElementById("stop-btn").hidden = true;
    document.getElementById("scan-result").innerHTML = "";
  }

  async function confirmAccess() {
    if (!verificationPayload) {
      return;
    }
    const button = document.getElementById("confirm-access");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';

    try {
      const { payload } = await fetchJson(config.confirmUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ codigo: verificationPayload.codigo }),
      });

      if (!payload.success) {
        showMessage("scan-result", "danger", payload.message);
        bootstrap.Modal.getOrCreateInstance(document.getElementById("verificationModal")).hide();
        return;
      }

      const attendee = payload.attendee;
      bootstrap.Modal.getOrCreateInstance(document.getElementById("verificationModal")).hide();
      showInfoModal(
        '<i class="fas fa-check-circle text-success"></i> Acceso autorizado',
        `
          <div class="text-center">
            <h3 class="text-success mb-3">${attendee.name}</h3>
            <p>Ingreso confirmado exitosamente.</p>
            <div class="row text-start mt-4">
              <div class="col-md-6">
                <p><strong>Cedula:</strong> ${attendee.cc}</p>
                <p><strong>Categoria:</strong> ${attendee.category}</p>
              </div>
              <div class="col-md-6">
                <p><strong>Fecha:</strong> ${attendee.date}</p>
                <p><strong>Hora:</strong> ${attendee.time}</p>
              </div>
            </div>
          </div>
        `
      );
      setTimeout(() => window.location.reload(), 1800);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
      verificationPayload = null;
    }
  }

  async function viewQr(cc) {
    const url = config.qrPattern.replace("__CC__", cc);
    const { payload } = await fetchJson(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!payload.success) {
      showInfoModal("Error", `<div class="alert alert-danger">${payload.message}</div>`);
      return;
    }
    const attendee = payload.attendee;
    showInfoModal(
      '<i class="fas fa-qrcode"></i> Codigo QR',
      `
        <div class="text-center">
          <h4>${attendee.name}</h4>
          <p><strong>Cedula:</strong> ${attendee.cc}</p>
          <p><strong>Categoria:</strong> ${attendee.category}</p>
          <p><strong>Precio:</strong> $ ${attendee.paid_amount}</p>
          <p><strong>Balance:</strong> ${attendee.balance}</p>
          ${payload.qr_url ? `<img src="${payload.qr_url}" alt="QR ${attendee.name}" class="img-fluid my-3">` : ""}
        </div>
      `
    );
  }

  async function markEntry(cc) {
    if (!window.confirm("Marcar este asistente como ingresado?")) {
      return;
    }
    const { payload } = await fetchJson(config.markUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ cc }),
    });
    if (!payload.success) {
      window.alert(payload.message);
      return;
    }
    window.location.reload();
  }

  async function deleteAttendee(cc) {
    if (!window.confirm("Eliminar este asistente permanentemente?")) {
      return;
    }
    const { payload } = await fetchJson(config.deleteUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ cc }),
    });
    if (!payload.success) {
      window.alert(payload.message);
      return;
    }
    await loadList(1);
    window.location.reload();
  }

  function syncPriceWithCategory() {
    const category = document.querySelector('#form-crear select[name="category"]');
    const paidAmount = document.querySelector('#form-crear input[name="paid_amount"]');
    if (!category || !paidAmount) {
      return;
    }
    category.addEventListener("change", () => {
      const selected = category.value;
      if (selected && Object.prototype.hasOwnProperty.call(config.categoryPrices, selected)) {
        const rawValue = config.categoryPrices[selected];
        paidAmount.value = window.NumberFormatting?.formatThousands
          ? window.NumberFormatting.formatThousands(rawValue, 0)
          : rawValue;
      }
    });
  }

  function normalizeContentTab(tabName) {
    const normalized = String(tabName || "").replace(/^#/, "");
    return CONTENT_TABS.has(normalized) ? normalized : "";
  }

  function normalizeModalTab(tabName) {
    const normalized = String(tabName || "").replace(/^#/, "");
    return MODAL_TABS.has(normalized) ? normalized : "";
  }

  function getStoredContentTab() {
    return normalizeContentTab(localStorage.getItem("entrada-active-tab"));
  }

  function getPreferredContentTab() {
    const requestedTab = normalizeContentTab(new URLSearchParams(window.location.search).get("tab"));
    const templateTab = normalizeContentTab(shell.dataset.initialTab);
    const storedTab = getStoredContentTab();
    return requestedTab || templateTab || storedTab || "scanner";
  }

  function restoreTab() {
    const searchParams = new URLSearchParams(window.location.search);
    const requestedTab = searchParams.get("tab");
    const contentTab = getPreferredContentTab();
    const modalTab =
      normalizeModalTab(searchParams.get("modal")) ||
      normalizeModalTab(config.openModal) ||
      normalizeModalTab(requestedTab) ||
      normalizeModalTab(shell.dataset.initialTab);

    activateTab(`#${contentTab}`);
    if (modalTab) {
      openOperationalModal(modalTab);
    }
  }

  function bindTabs() {
    document.querySelectorAll('#entrada-tabs [data-bs-toggle="tab"]').forEach((tab) => {
      tab.addEventListener("shown.bs.tab", (event) => {
        localStorage.setItem("entrada-active-tab", event.target.dataset.bsTarget);
      });
    });
  }

  function activateTab(targetSelector) {
    const trigger = document.querySelector(`[data-bs-target="${targetSelector}"]`);
    if (trigger) {
      bootstrap.Tab.getOrCreateInstance(trigger).show();
      return;
    }

    const paneId = targetSelector.replace(/^#/, "");
    document.querySelectorAll(".tab-pane").forEach((pane) => {
      const isActive = pane.id === paneId;
      pane.classList.toggle("show", isActive);
      pane.classList.toggle("active", isActive);
    });
    localStorage.setItem("entrada-active-tab", targetSelector);
  }

  function bindAnalyticsToggle() {
    const toggle = document.getElementById("analytics-toggle");
    const content = document.getElementById("analytics-content");
    if (!toggle || !content) {
      return;
    }

    const storageKey = "entrada-analytics-open";
    const applyState = (isOpen) => {
      toggle.setAttribute("aria-expanded", String(isOpen));
      content.hidden = !isOpen;
      content.classList.toggle("is-open", isOpen);
    };

    const saved = localStorage.getItem(storageKey);
    applyState(saved !== "false");

    toggle.addEventListener("click", () => {
      const nextState = toggle.getAttribute("aria-expanded") !== "true";
      applyState(nextState);
      localStorage.setItem(storageKey, String(nextState));
    });
  }

  function openCategoryModal(returnTab = "crear") {
    const returnField = document.querySelector("[data-category-return-tab]");
    if (returnField) {
      returnField.value = normalizeContentTab(returnTab) || getPreferredContentTab();
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById("categoryModal")).show();
  }

  function openEventDayModal() {
    bootstrap.Modal.getOrCreateInstance(document.getElementById("eventDayModal")).show();
  }

  function openExpenseModal() {
    bootstrap.Modal.getOrCreateInstance(document.getElementById("expenseModal")).show();
  }

  function openCashDropModal() {
    bootstrap.Modal.getOrCreateInstance(document.getElementById("cashDropModal")).show();
  }

  function openOperationalModal(tab) {
    if (tab === "categorias") {
      openCategoryModal(getPreferredContentTab());
      return;
    }
    if (tab === "evento-dia") {
      openEventDayModal();
      return;
    }
    if (tab === "gastos") {
      openExpenseModal();
      return;
    }
    if (tab === "vaciar-caja") {
      openCashDropModal();
    }
  }

  function clearModalTabQuery(tabName) {
    const url = new URL(window.location.href);
    if (url.searchParams.get("tab") === tabName) {
      url.searchParams.delete("tab");
      window.history.replaceState({}, "", url);
    }
  }

  function bindModalCleanup(modalId, tabName) {
    const modalElement = document.getElementById(modalId);
    if (!modalElement) {
      return;
    }
    modalElement.addEventListener("hidden.bs.modal", () => {
      clearModalTabQuery(tabName);
      if (!document.querySelector(".tab-pane.active")) {
        activateTab(localStorage.getItem("entrada-active-tab") || "#scanner");
      }
    });
  }

  function toggleSingleTransferProof(selectElement) {
    const form = selectElement.closest("form");
    const proofRow = form?.querySelector("[data-single-transfer-proof]");
    if (!proofRow) {
      return;
    }
    proofRow.classList.toggle("d-none", selectElement.value !== "transferencia");
  }

  function bindSinglePaymentForms() {
    document.querySelectorAll('select[name="payment_method"]').forEach((selectElement) => {
      toggleSingleTransferProof(selectElement);
      selectElement.addEventListener("change", () => toggleSingleTransferProof(selectElement));
    });
  }

  function refreshEventDayTotal() {
    const quantityInput = document.querySelector('#event-day-form input[name="attendee_quantity"]');
    const unitAmountInput = document.querySelector('#event-day-form input[name="unit_amount"]');
    const target = document.getElementById("event-day-total-display");
    if (!quantityInput || !unitAmountInput || !target) {
      return;
    }
    const parseInput = (value) => {
      const normalized = String(value || "").replace(/\./g, "").replace(",", ".");
      const parsed = Number(normalized);
      return Number.isFinite(parsed) ? parsed : 0;
    };
    const total = parseInput(quantityInput.value) * parseInput(unitAmountInput.value);
    const formatter = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    target.textContent = `$ ${formatter.format(total)}`;
  }

  function bindEventDayCalculator() {
    const quantityInput = document.querySelector('#event-day-form input[name="attendee_quantity"]');
    const unitAmountInput = document.querySelector('#event-day-form input[name="unit_amount"]');
    if (!quantityInput || !unitAmountInput) {
      return;
    }
    quantityInput.addEventListener("input", refreshEventDayTotal);
    unitAmountInput.addEventListener("input", refreshEventDayTotal);
    quantityInput.addEventListener("blur", refreshEventDayTotal);
    unitAmountInput.addEventListener("blur", refreshEventDayTotal);
    refreshEventDayTotal();
  }

  function bindPaymentBreakdown() {
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
        if (!addButton) {
          return;
        }
        addButton.disabled = !rows.some((row) => row.classList.contains("d-none"));
      };

      const clearRow = (row) => {
        row.querySelectorAll("input").forEach((input) => {
          input.value = "";
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
          if (!row) {
            return;
          }
          const visibleRows = rows.filter((item) => !item.classList.contains("d-none"));
          clearRow(row);
          if (visibleRows.length > 1) {
            row.classList.add("d-none");
          }
          updateVisibleRows();
          syncAddButton();
        });
      });
      updateVisibleRows();
      syncAddButton();
    });
  }

  function bindCategoryModal() {
    document.getElementById("open-category-modal-btn")?.addEventListener("click", () => openCategoryModal("crear"));
    bindModalCleanup("categoryModal", "categorias");
    bindModalCleanup("eventDayModal", "evento-dia");
    bindModalCleanup("expenseModal", "gastos");
    bindModalCleanup("cashDropModal", "vaciar-caja");
  }

  function openScannerTab() {
    activateTab("#scanner");
    document.getElementById("scanner")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function shareFilesToWhatsApp(button) {
    const whatsappWebUrl = button.dataset.whatsappWebUrl || "";
    const qrFileUrl = button.dataset.qrFileUrl || "";
    const shareCardUrl = button.dataset.shareCardUrl || "";
    const imageUrl = qrFileUrl || shareCardUrl;

    try {
      if (
        imageUrl &&
        navigator.clipboard &&
        window.ClipboardItem
      ) {
        const response = await fetch(imageUrl, { credentials: "same-origin" });
        if (response.ok) {
          const blob = await response.blob();
          await navigator.clipboard.write([
            new ClipboardItem({
              [blob.type || "image/png"]: blob,
            }),
          ]);
          if (whatsappWebUrl) {
            window.open(whatsappWebUrl, "_blank", "noopener,noreferrer");
          }
          showInfoModal(
            "WhatsApp Web abierto",
            '<div class="alert alert-warning mb-0">Se abrio WhatsApp Web y se copio el QR al portapapeles. En el chat pega con <strong>Ctrl+V</strong> para enviarlo como imagen.</div>'
          );
          return;
        }
      }
    } catch (error) {
      // Fall through to the manual guidance modal.
    }

    if (whatsappWebUrl) {
      window.open(whatsappWebUrl, "_blank", "noopener,noreferrer");
    }

    showInfoModal(
      "WhatsApp Web abierto",
      '<div class="alert alert-warning mb-0">Se abrio WhatsApp Web en una pestaña nueva. Si la imagen no se copio automaticamente, arrastra el QR o el flyer manualmente al chat.</div>'
    );
  }

  document.getElementById("start-btn")?.addEventListener("click", startScanner);
  document.getElementById("stop-btn")?.addEventListener("click", stopScanner);
  document.getElementById("floating-scanner-button")?.addEventListener("click", openScannerTab);
  document.querySelectorAll("[data-whatsapp-share]").forEach((button) => {
    button.addEventListener("click", (event) => shareFilesToWhatsApp(event.currentTarget));
  });
  document.getElementById("refresh-list-btn")?.addEventListener("click", () => loadList(1));
  document.getElementById("confirm-access")?.addEventListener("click", confirmAccess);
  document.getElementById("verificationModal")?.addEventListener("hidden.bs.modal", () => {
    if (!document.getElementById("stop-btn").hidden) {
      isScanning = true;
    }
    verificationPayload = null;
  });

  document.getElementById("filtro-buscar")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadList(1);
    }
  });
  document.getElementById("filtro-estado")?.addEventListener("change", () => loadList(1));

  window.irAPagina = (page) => loadList(page);
  window.verQR = viewQr;
  window.marcarIngreso = markEntry;
  window.eliminarAsistente = deleteAttendee;

  const postCreateNoticeModal = document.getElementById("postCreateNoticeModal");
  if (postCreateNoticeModal) {
    bootstrap.Modal.getOrCreateInstance(postCreateNoticeModal).show();
  }

  formatNumbers();
  bindListFooter();
  bindTabs();
  bindAnalyticsToggle();
  bindCategoryModal();
  bindPaymentBreakdown();
  bindSinglePaymentForms();
  bindEventDayCalculator();
  restoreTab();
  syncPriceWithCategory();
})();
