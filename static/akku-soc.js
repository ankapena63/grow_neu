// Variablen für Modal
const socModalEl = document.getElementById('socModal');
const socModal = new bootstrap.Modal(socModalEl);
const socRange = document.getElementById('socModalRange');
const socValue = document.getElementById('socModalValue');
const socLabel = document.getElementById('socModalLabelField');

let currentField = null;

// Klick auf SOC-Feld
document.querySelectorAll('.soc-editable').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
        currentField = el.id;
        // aktuellen Wert aus dem Feld lesen
        const match = el.textContent.match(/\d+/);
        const val = match ? parseInt(match[0]) : 0;
        // Bereich festlegen
        if (currentField === "dischargeSocLimit") {
            socLabel.textContent = "⬇️ Min SOC";
            socRange.min = 1;
            socRange.max = 30;
        } else if (currentField === "chargeSocLimit") {
            socLabel.textContent = "⬆️ Max SOC";
            socRange.min = 70;
            socRange.max = 100;
        }
        // Wert innerhalb des erlaubten Bereichs halten
        socRange.value = Math.min(
            Math.max(val, Number(socRange.min)),
            Number(socRange.max)
        );
        socValue.textContent = socRange.value;
        // Modal zeigen
        socModal.show();
    });
});
// Range Wert bei Bewegung updaten
socRange.addEventListener('input', () => {
    socValue.textContent = socRange.value;
});

// Speichern Button
document.getElementById('socModalSave').addEventListener('click', async () => {
    const val = parseInt(socRange.value);
    const el = document.getElementById(currentField);
    let bezeichnung = "";
    let icon = "";
    if (currentField === "dischargeSocLimit") {
        bezeichnung = "Min SOC";
        icon = "⬇️";
    } else if (currentField === "chargeSocLimit") {
        bezeichnung = "Max SOC";
        icon = "⬆️";
    }
try {
    const res = await fetch('/update_soc', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            id: currentField,
            value: val
        })
    });
    const data = await res.json();
    // HTTP-Fehler oder Backend-Fehler
    if (!res.ok) {
        throw new Error(
            data.error || 'SOC konnte nicht gespeichert werden'
        );
    }
    el.textContent = currentField === "dischargeSocLimit"
    ? `⬇️ ${val}%`
    : `⬆️ ${val}%`;
    // Erfolg
    const toastEl = document.getElementById('socToast');
    const toastBody = document.getElementById('socToastBody');

    toastBody.innerText =
        `${icon} ${bezeichnung} auf ${val}% gespeichert`;

    const toast = new bootstrap.Toast(toastEl, {
        delay: 5000
    });
    toast.show();
} catch (err) {
    console.error('[SOC]', err);
    alert(`Fehler: ${err.message}`);
    return;
}
    socModal.hide();
});
