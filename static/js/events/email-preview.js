const emailPreviewCard = document.querySelector("[data-email-preview-card]");

if (emailPreviewCard) {
  const outputs = {
    subject: document.querySelector('[data-email-preview-output="subject"]'),
    preheader: document.querySelector('[data-email-preview-output="preheader"]'),
    heading: document.querySelector('[data-email-preview-output="heading"]'),
    intro: document.querySelector('[data-email-preview-output="intro"]'),
    messageTitle: document.querySelector('[data-email-preview-output="messageTitle"]'),
    body: document.querySelector('[data-email-preview-output="body"]'),
    warningTitle: document.querySelector('[data-email-preview-output="warningTitle"]'),
    warningText: document.querySelector('[data-email-preview-output="warningText"]'),
    detailsTitle: document.querySelector('[data-email-preview-output="detailsTitle"]'),
    dateText: document.querySelector('[data-email-preview-output="dateText"]'),
    timeText: document.querySelector('[data-email-preview-output="timeText"]'),
    venue: document.querySelector('[data-email-preview-output="venue"]'),
    mapsLabel: document.querySelector('[data-email-preview-output="mapsLabel"]'),
    mapsLink: document.querySelector('[data-email-preview-output="mapsLink"]'),
    dressCode: document.querySelector('[data-email-preview-output="dressCode"]'),
    qrTitle: document.querySelector('[data-email-preview-output="qrTitle"]'),
    qrNote: document.querySelector('[data-email-preview-output="qrNote"]'),
    qrImage: document.querySelector('[data-email-preview-output="qrImage"]'),
    footer: document.querySelector('[data-email-preview-output="footer"]'),
    closingText: document.querySelector('[data-email-preview-output="closingText"]'),
    teamSignature: document.querySelector('[data-email-preview-output="teamSignature"]'),
    legalNote: document.querySelector('[data-email-preview-output="legalNote"]'),
    eventName: document.querySelector('[data-email-preview-output="event-name"]'),
    eventNameSecondary: document.querySelector('[data-email-preview-output="event-name-secondary"]'),
    eventDate: document.querySelector('[data-email-preview-output="event-date"]'),
    branch: document.querySelector('[data-email-preview-output="branch"]'),
    flyerImage: document.querySelector('[data-email-preview-output="flyer-image"]'),
  };
  const flyerWrap = document.querySelector(".email-preview-flyer-wrap");
  const qrCard = document.querySelector("[data-email-preview-qr-card]");
  const eventForm = document.getElementById("event-form");
  const qrPreviewUrl = eventForm?.dataset.qrPreviewUrl || "";
  let qrPreviewController = null;

  const sampleContext = {
    attendee_name: "Andrea",
    nombre_asistente: "Andrea",
    event_name: "Evento Demo",
    nombre_evento: "Evento Demo",
    branch_name: outputs.branch?.textContent || "Sucursal Principal",
    nombre_sucursal: outputs.branch?.textContent || "Sucursal Principal",
    event_date: "14/03/2026 20:00",
    fecha_evento: "14/03/2026 20:00",
    event_time: "8:00 PM",
    hora_evento: "8:00 PM",
    category_name: "VIP",
    nombre_categoria: "VIP",
    qr_code: "DMT-EVT-ABCD1234",
    codigo_qr: "DMT-EVT-ABCD1234",
    attendee_cc: "1234567890",
    cedula_asistente: "1234567890",
    category_price: "45000",
    precio_categoria: "45000",
  };

  const formatDateTimeInput = (value) => {
    if (!value) {
      return { date: sampleContext.event_date, time: sampleContext.event_time };
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return { date: value, time: value };
    }

    return {
      date: new Intl.DateTimeFormat("es-CO", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date),
      time: new Intl.DateTimeFormat("es-CO", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      }).format(date),
    };
  };

  const applyTemplate = (value) =>
    (value || "").replace(/\{(\w+)\}/g, (_, key) => sampleContext[key] ?? `{${key}}`);

  const syncPreviewEditToField = (element) => {
    const fieldId = element.dataset.previewInput;
    const field = fieldId ? document.getElementById(fieldId) : null;
    if (!field) {
      return;
    }
    const value = element.innerText.replace(/\u00a0/g, " ").trim();
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const bindDirectPreviewEditing = () => {
    document.querySelectorAll("[data-preview-input]").forEach((element) => {
      element.setAttribute("contenteditable", "true");
      element.setAttribute("spellcheck", "false");
      element.addEventListener("click", (event) => {
        if (element.closest("a")) {
          event.preventDefault();
        }
      });
      element.addEventListener("input", () => syncPreviewEditToField(element));
      element.addEventListener("blur", () => syncPreviewEditToField(element));
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !["DIV", "P"].includes(element.tagName)) {
          event.preventDefault();
          element.blur();
        }
      });
    });
  };

  const bindFilePreview = (fieldName, selectedLabel) => {
    const input = document.getElementById(`id_${fieldName}`);
    const card = document.querySelector(`[data-file-preview-card="${fieldName}"]`);
    const image = document.querySelector(`[data-file-preview-image="${fieldName}"]`);
    const name = document.querySelector(`[data-file-preview-name="${fieldName}"]`);
    const label = document.querySelector(`[data-file-preview-label="${fieldName}"]`);
    if (!input || !card || !image || !name || !label) {
      return;
    }

    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) {
        return;
      }

      const reader = new FileReader();
      reader.onload = ({ target }) => {
        image.src = target?.result || "";
        name.textContent = file.name;
        label.textContent = selectedLabel;
        card.hidden = false;
      };
      reader.readAsDataURL(file);
    });
  };

  const refreshQrPreview = () => {
    if (!outputs.qrImage || !eventForm || !qrPreviewUrl) {
      return;
    }

    if (qrPreviewController) {
      qrPreviewController.abort();
    }
    qrPreviewController = new AbortController();

    const formData = new FormData();
    formData.append("csrfmiddlewaretoken", document.querySelector("[name=csrfmiddlewaretoken]")?.value || "");
    formData.append("code", sampleContext.qr_code);
    formData.append("event_id", eventForm.dataset.eventId || "");
    [
      "qr_fill_color",
      "qr_background_color",
      "qr_logo_background_color",
      "qr_logo_scale",
    ].forEach((fieldName) => {
      const field = document.getElementById(`id_${fieldName}`);
      if (field?.value) {
        formData.append(fieldName, field.value);
      }
    });

    ["logo"].forEach((fieldName) => {
      const field = document.getElementById(`id_${fieldName}`);
      const file = field?.files?.[0];
      if (file) {
        formData.append(fieldName, file);
      }
    });

    fetch(qrPreviewUrl, {
      method: "POST",
      body: formData,
      signal: qrPreviewController.signal,
    })
      .then((response) => response.json())
      .then((payload) => {
        if (payload.success && payload.image) {
          outputs.qrImage.src = payload.image;
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          console.error("No se pudo actualizar el preview del QR.", error);
        }
      });
  };

  const setHtmlOutput = (target, value) => {
    if (outputs[target]) {
      outputs[target].innerHTML = applyTemplate(value).replace(/\n/g, "<br>");
    }
  };

  const setTextOutput = (target, value) => {
    if (outputs[target]) {
      outputs[target].textContent = applyTemplate(value);
    }
  };

  const updatePreview = () => {
    const eventNameInput = document.getElementById("id_name");
    const eventDateInput = document.getElementById("id_starts_at");
    const flyerInput = document.getElementById("id_flyer");
    const mapsUrlInput = document.getElementById("id_maps_url");

    if (eventNameInput?.value) {
      sampleContext.event_name = eventNameInput.value;
      sampleContext.nombre_evento = eventNameInput.value;
    }

    const dateContext = formatDateTimeInput(eventDateInput?.value || "");
    sampleContext.event_date = dateContext.date;
    sampleContext.fecha_evento = dateContext.date;
    sampleContext.event_time = dateContext.time;
    sampleContext.hora_evento = dateContext.time;

    document.querySelectorAll("[data-email-preview]").forEach((input) => {
      const target = input.dataset.emailPreview;
      const value = input.value || input.placeholder || "";

      if (target === "background") {
        emailPreviewCard.style.setProperty("--email-bg", input.value || "#f6f2eb");
        return;
      }
      if (target === "qrFill" || target === "qrBackground" || target === "qrLogoBackground" || target === "qrLogoScale") {
        return;
      }
      if (target === "card") {
        emailPreviewCard.style.setProperty("--email-card", input.value || "#ffffff");
        return;
      }
      if (target === "headerBackground") {
        emailPreviewCard.style.setProperty("--email-header-bg", input.value || "#111315");
        return;
      }
      if (target === "text") {
        emailPreviewCard.style.setProperty("--email-text", input.value || "#172121");
        return;
      }
      if (target === "muted") {
        emailPreviewCard.style.setProperty("--email-muted", input.value || "#bdbdbd");
        return;
      }
      if (target === "accent") {
        emailPreviewCard.style.setProperty("--email-accent", input.value || "#c44536");
        return;
      }
      if (target === "border") {
        emailPreviewCard.style.setProperty("--email-border", input.value || "#1f1f22");
        return;
      }
      if (target === "section") {
        emailPreviewCard.style.setProperty("--email-section", input.value || "#18191b");
        return;
      }
      if (target === "warning") {
        emailPreviewCard.style.setProperty("--email-warning", input.value || "#2a1c17");
        return;
      }
      if (["intro", "body", "warningText"].includes(target)) {
        setHtmlOutput(target, value);
        return;
      }
      if (target === "mapsUrl") {
        if (outputs.mapsLink) {
          outputs.mapsLink.href = value || "#";
        }
        return;
      }
      setTextOutput(target, value);
    });

    if (outputs.subject) {
      outputs.subject.textContent = applyTemplate(
        document.getElementById("id_email_subject")?.value ||
          document.getElementById("id_email_subject")?.placeholder ||
          "",
      );
    }

    if (outputs.eventName) {
      outputs.eventName.textContent = sampleContext.event_name;
    }
    if (outputs.eventNameSecondary) {
      outputs.eventNameSecondary.textContent = sampleContext.event_name;
    }
    if (outputs.eventDate) {
      outputs.eventDate.textContent = sampleContext.event_date;
    }
    if (outputs.mapsLabel && !outputs.mapsLabel.textContent.trim()) {
      outputs.mapsLabel.textContent = "Abrir en Google Maps";
    }
    if (outputs.mapsLink && mapsUrlInput && !mapsUrlInput.value) {
      outputs.mapsLink.removeAttribute("href");
    }
    if (flyerInput && outputs.flyerImage && flyerWrap) {
      const file = flyerInput.files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = ({ target }) => {
          outputs.flyerImage.src = target?.result || "";
          flyerWrap.classList.remove("is-empty");
        };
        reader.readAsDataURL(file);
      } else if (outputs.flyerImage.getAttribute("src")) {
        flyerWrap.classList.remove("is-empty");
      } else {
        flyerWrap.classList.add("is-empty");
      }
    }

    refreshQrPreview();
  };

  document.querySelectorAll("#event-form input, #event-form textarea, #event-form select").forEach((input) => {
    input.addEventListener("input", updatePreview);
    input.addEventListener("change", updatePreview);
  });

  bindFilePreview("logo", "Logo seleccionado");
  bindFilePreview("flyer", "Flyer seleccionado");
  bindDirectPreviewEditing();
  updatePreview();
}
