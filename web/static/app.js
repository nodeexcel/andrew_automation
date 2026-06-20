async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    const pill = document.getElementById("status-pill");
    const statusText = document.getElementById("status-text");
    const dashStatus = document.getElementById("dash-status");

    if (pill && statusText) {
      pill.classList.toggle("running", data.running);
      pill.classList.toggle("stopped", !data.running);
      statusText.textContent = data.running ? "Running" : "Stopped";
    }

    if (dashStatus) {
      dashStatus.textContent = data.running ? "Running" : "Stopped";
      dashStatus.classList.toggle("text-success", data.running);
      dashStatus.classList.toggle("text-muted", !data.running);
    }
  } catch (_) {
    /* ignore polling errors */
  }
}

setInterval(refreshStatus, 5000);
