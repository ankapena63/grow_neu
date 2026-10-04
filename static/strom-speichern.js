/* Blendet die Zusatzoptionen sofort ein/aus, wenn Nulleinspeisung geschaltet wird. */

function toggleZusatzOptionen(isNulleinspeisungActive) {
    const container = document.getElementById('zusatzOptionen');
    container.classList.toggle('d-none', isNulleinspeisungActive);
}
/*  Event-Listener für den Übernehmen-Button.
 * Sammelt alle Daten und sendet sie gesammelt an Quart. */
document.addEventListener('click', async function(event) {
    if (event.target && event.target.id === 'btnSpeichern') {
        const settings = {}; 
        // Alle Schalter (auch die versteckten) einsammeln
        document.querySelectorAll('.dropdown-menu .form-check-input').forEach(sw => {
            settings[sw.id] = sw.checked;
        });
        console.log("Speichere Einstellungen:", settings);
        try {
            const response = await fetch('/update_einstellung', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            if (response.ok) {
                // Seite neu laden: Schließt Fenster & aktualisiert Jinja-Ansicht (Farben etc.)
                window.location.reload();
            } else {
                const err = await response.json();
                alert("Fehler: " + (err.error || "Serverfehler"));
            }
        } catch (err) {
            console.error("Netzwerkfehler:", err);
            alert("Verbindung zum Server fehlgeschlagen!");
        }
    }
});
