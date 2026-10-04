window.kochen_active = false;
window.kochen_zeit = 0;
function kochenClick() {
    // WENN AKTIV -> STOP FRAGE
    if (window.kochen_active) {
        if (confirm("Kochen ausschalten?")) {
            fetch("/kochen_stop", {
                method: "POST"
            });
        }
    } else {
        // AKTUELLE WERTE IN MODAL        
        setKnobValue(window.kochen_zeit || 0);
        document.getElementById("m_soc").value =window.kochen_soc_min || 40;
        document.getElementById("m_watt").value = window.kochen_wert || 1400;
        // MODAL ÖFFNEN
        document.getElementById("kochen_modal").classList.add("is-open");
    }
}
function closeKochenModal() {
    document.getElementById("kochen_modal").classList.remove("is-open");
}

function startKochen() {
    let zeit = parseInt(document.getElementById("m_zeit").value);
    let soc = parseInt(document.getElementById("m_soc").value);
    let watt = parseInt(document.getElementById("m_watt").value);
    // ZEIT
    if (zeit <= 0) {
        alert("Zeit muss größer 0 sein");
        return;
    }
    // SOC BEREICH
    if (soc < 30 || soc > 90) {
        alert("SOC muss zwischen 30 und 90 sein");
        return;
    }
    // WATT
    if (watt < 100 || watt > 3000) {
        alert("Watt muss zwischen 100 und 3000 sein");
        return;
    } // SOC GEGEN AKKU

    const data = {
        kochen: true,
        kochen_zeit: zeit,
        kochen_soc_min: soc,
        kochen_wert: watt
    };
fetch("/kochen_start", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
})
.then(r => r.json())
.then(r => {
    if(!r.ok){
        alert(r.fehler || "Kochen konnte nicht gestartet werden");
        return;
    }
    closeKochenModal();
     // Anzeige sofort aktualisieren
    updateKochen(r);
});
}
function updateKochen(e) {
    const btn = document.getElementById("kochen_btn");
    // GLOBAL SPEICHERN
    window.kochen_active = e.kochen;
    window.kochen_zeit = e.kochen_zeit;
    window.kochen_soc_min = e.kochen_soc_min;
    window.kochen_wert = e.kochen_wert;
    // AKTIV
    if (e.kochen) {
        btn.classList.add("kochen-button-active");
btn.innerHTML = `
    <div class="d-flex align-items-center justify-content-center gap-3">
        <div class="fw-bold">
            🍳 KOCHEN
        </div>
        <div
            class="fw-bold kochen-countdown">
            ⏱️ ${e.kochen_zeit}
        </div>
        <div class="small"> min </div>
    </div>
    <div class="small mt-1">
      dazu  ⚡ ${e.kochen_wert} Watt |
      bis  🔋 ${e.kochen_soc_min} % SOC
    </div>
`;
    } else {

        btn.classList.remove("kochen-button-active");
        btn.innerHTML = `
            🍳 KOCHEN AUS
        `;
    }
}

let knobValue = 0;
function setKnobValue(val){
    val = Math.max(0, Math.min(240, val));
    knobValue = val;
    document.getElementById("m_zeit").value = val;
    document.getElementById("m_zeit_t").textContent = val;
    const deg = (val / 240) * 360;
    document.getElementById("zeit_knob").style.setProperty(
        "--knob-progress",
        `${deg}deg`
    );
}
function rotateKnob(event){
    const knob = document.getElementById("zeit_knob");
    const rect = knob.getBoundingClientRect();
    const x =
        event.touches[0].clientX -
        rect.left -
        rect.width / 2;
    const y =
        event.touches[0].clientY -
        rect.top -
        rect.height / 2;
    let angle =
        Math.atan2(y, x) * 180 / Math.PI + 90;
    if(angle < 0){
        angle += 360;
    }
    const value = Math.round((angle / 360) * 48) * 5;
    setKnobValue(value);
}

function mouseRotate(event){
    if(event.buttons !== 1){
        return;
    }
    const knob = document.getElementById("zeit_knob");
    const rect = knob.getBoundingClientRect();
    const x =
        event.clientX -
        rect.left -
        rect.width / 2;
    const y =
        event.clientY -
        rect.top -
        rect.height / 2;
    let angle =
        Math.atan2(y, x) * 180 / Math.PI + 90;
    if(angle < 0){
        angle += 360;
    }
    const value =Math.round((angle / 360) * 48) * 5;
    setKnobValue(value);
}
setKnobValue(0);

window.onclick = function(e) {
    const m = document.getElementById("kochen_modal");
    if (e.target === m) {
        m.classList.remove("is-open");
    }
}
