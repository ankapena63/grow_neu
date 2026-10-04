function confirmSSH() {
    const status = document.getElementById("ssh-toggle")?.dataset.toggleStatus ?? "an";
    if (confirm("Willst du den SSH Server wirklich " + status + " machen?")) {
        document.getElementById("sshForm").submit();
    }
}

async function toggleNachtSchalter() {
    const btn = document.getElementById("switch-nacht-btn");
    const newStatus = btn?.dataset.nextStatus === "true";
    let text = "";
    if (newStatus) {
        text = "aktivieren, dann wird nur 0-Einspeisung gemacht";
    } else {
        text = "deaktivieren, andere Modi sind möglich";
    }
    if (!confirm(
        "Willst du den Nachtmodus-Schalter wirklich " + text + "?"
    )) {
        return;
    }
    try {
        const response = await fetch("/update_einstellung", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                switchNacht: newStatus
            })
        });
        const data = await response.json();
        if (data.success) {
            location.reload();
        } else {
            alert(
                "Fehler beim Umschalten: " +
                (data.error || "Unbekannter Fehler")
            );
        }
    } catch (err) {
        alert("Fehler beim Ajax-Aufruf: " + err);
        console.error(err);
    }
}
