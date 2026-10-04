function showSettingsToast(message, isSuccess, duration) {
    const toast = document.createElement("div");
    toast.className = `toast align-items-center ${
        isSuccess ? "text-bg-success" : "text-bg-danger"
    } border-0 show`;
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "assertive");
    toast.setAttribute("aria-atomic", "true");

    const content = document.createElement("div");
    content.className = "d-flex";

    const body = document.createElement("div");
    body.className = "toast-body";
    body.textContent = message;

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "btn-close btn-close-white me-2 m-auto";
    closeButton.setAttribute("data-bs-dismiss", "toast");
    closeButton.setAttribute("aria-label", "Schließen");
    closeButton.addEventListener("click", () => toast.remove());

    content.append(body, closeButton);
    toast.append(content);
    document.getElementById("toastContainer").append(toast);
    window.setTimeout(() => toast.remove(), duration);
}

async function saveSettings(event) {
    event.preventDefault();
    const form = event.currentTarget;

    try {
        const response = await fetch("/update", {
            method: "POST",
            body: new FormData(form)
        });
        const result = await response.json();
        const succeeded = response.ok && (result.success ?? false);
        showSettingsToast(
            result.message || (
                succeeded
                    ? "Einstellungen gespeichert!"
                    : "Fehler beim Speichern!"
            ),
            succeeded,
            3000
        );
    } catch (error) {
        const message = error instanceof Error
            ? error.message
            : String(error);
        showSettingsToast(`Fehler beim Senden: ${message}`, false, 5000);
        console.error("Fehler beim Speichern:", error);
    }
}

document
    .getElementById("settingsForm")
    .addEventListener("submit", saveSettings);

document
    .getElementById("shutdownForm")
    .addEventListener("submit", async (event) => {
        if (event.defaultPrevented) {
            return;
        }
        event.preventDefault();
        const form = event.currentTarget;
        const button = form.querySelector("button[type='submit']");
        button.disabled = true;

        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: { "X-Shutdown-Handshake": "1" }
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || "Server konnte nicht beendet werden.");
            }
            button.textContent = "Server wird beendet …";
            fetch("/shutdown/confirm", { method: "POST" }).catch((error) => {
                console.error("Fehler beim Bestätigen der Server-Abschaltung:", error);
            });
        } catch (error) {
            button.disabled = false;
            const message = error instanceof Error
                ? error.message
                : String(error);
            showSettingsToast(message, false, 5000);
        }
    });
