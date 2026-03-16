const checkInForm = document.getElementById("checkin-form");

if (checkInForm) {
  checkInForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = document.getElementById("checkin-result");
    const formData = new FormData(checkInForm);

    const response = await fetch(checkInForm.dataset.endpoint, {
      method: "POST",
      body: formData,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json();
    result.innerHTML = `<div class="alert alert-${payload.success ? "success" : "warning"}">${payload.message}</div>`;
    if (payload.success) {
      checkInForm.reset();
      window.location.reload();
    }
  });
}

