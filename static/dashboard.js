function toggleAktuellMitBestaetigung(checkbox) {
    const neuerStatus = checkbox.checked;
    const text = neuerStatus
        ? "Sollen die Daten für 48 Stunden gespeichert werden?"
        : "Sollen die 48-Stunden-Daten nicht mehr gespeichert werden?";
    if (!confirm(text)) {
        checkbox.checked = !neuerStatus;
        return;
    }
    toggleAktuell();
}

function aktualisiereAktuellAnzeige(aktiv) {
    const checkbox = document.getElementById("aktuellAktiv");
    const text = document.getElementById("aktuellSwitchText");
    const box = document.getElementById("aktuellSwitchBox");

    if (checkbox) checkbox.checked = aktiv;
    if (text) text.textContent = aktiv ? "Daten: 48h AN" : "Daten: 48h AUS";
    if (box) box.style.backgroundColor = aktiv ? "#dc3545" : "#198754";
}

async function toggleAktuell() {
    const checkbox = document.getElementById("aktuellAktiv");
    if (!checkbox) return;

    const aktiv = checkbox.checked;
    try {
        const antwort = await fetch("/api/toggle_aktuell", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                aktuell_aktiv: aktiv
            })
        });
        if (!antwort.ok) {
            throw new Error("HTTP " + antwort.status);
        }
        const daten = await antwort.json();
        if (typeof daten.aktuell_aktiv !== "boolean") {
            throw new Error("Ungültige Antwort vom Server");
        }
        aktualisiereAktuellAnzeige(daten.aktuell_aktiv);
    } catch (err) {
        console.error("Fehler beim Umschalten:", err);
        checkbox.checked = !aktiv;
        aktualisiereAktuellAnzeige(!aktiv);
        alert("Die Einstellung konnte nicht geändert werden.");
    }
}

let zeitDiffMillis = 0;
let diffInterval = null;
let lastNoahZeit = null;
const interval = Number(document.body.dataset.refreshInterval) || 4000;

function set_text(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? "--";
}

function finite_number(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function set_mit_runden(id, value, komma_ = 2, faktor = 1) {
    const number = finite_number(value);
    if (number === null) {
        set_text(id, "--");
        return;
    }

    set_text(id, (number * faktor).toFixed(komma_));
}

let aktuelleDaten = null;

async function ladeDaten() {
    try {
        const response = await fetch("/api/daten");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!data || typeof data !== "object" || Array.isArray(data)) {
            throw new Error("Ungültige Datenantwort");
        }

        aktuelleDaten = data;
        updateDatenAlter(data);

        const d = data.daten ?? {};
        const akku = d.akku ?? {};
        const hms = d.hms ?? {};
        const solax = d.solax ?? {};
        const strom = d.strom ?? {};
        const t = data.tag_daten ?? {};
        const s_l = data.solax_local ?? {};
        const e = data.einstellungen ?? {};
        const k = data.kochen;
        const w = data.web ?? {};
        const status = data.status ?? {};

        set_text("statusHms", statusText(status.hms));
        set_text("statusSolaxL", statusText(status.solax_l));
        set_text("statusSolaxC", statusText(status.solax_c));
        set_text("statusAkku", statusText(status.akku_token));
        set_text("statusAkkuLogin", statusText(status.akku_login));
        set_text("statusStrom", statusText(status.strom));
        set_text("statusTuya", statusText(status.dose));

        if (typeof updateKochen === "function" && k) {
            updateKochen(k);
        }

        const toggleNullButton = document.getElementById("toggle-null-btn");
        if (toggleNullButton && typeof e.nur_nulleinspeisung === "boolean") {
            toggleNullButton.textContent = e.nur_nulleinspeisung
                ? "Nur 0 Einsp.⬇️"
                : "Gemischte ⬇️";
            toggleNullButton.style.backgroundColor = e.nur_nulleinspeisung
                ? "#f3061e"
                : "#0eeb42";
            toggleNullButton.style.color = e.nur_nulleinspeisung
                ? "white"
                : "black";
        }

        set_text("dazu_intervall", w.dazu_intervall);
        set_text("max_soc", e.max_soc);
        set_text("dazu", w.dazu);
        set_text("mittel_verbrauch", e.mittel_verbrauch);
        set_text("dazu_sanft", e.dazu_sanft);
        set_text("dazu_sanft_soc", w.dazu_sanft_soc);
        set_text("max_limit", e.max_limit);
        set_text("ppv_mittelwert", w.ppv_mittelwert);
        set_text("solax_l_mittelwert", w.solax_l_mittelwert);
        set_text("ppv_soc_ab", e.ppv_soc_ab);
        set_text("stunden_bis_nacht", w.stunden_bis_nacht);
        set_mit_runden("stunden_bis_nacht2", w.stunden_bis_nacht);
        set_mit_runden("brauche_watt", w.brauche_watt, 0);
        set_mit_runden("pro_stunde", w.pro_stunde, 0);
        set_mit_runden("haus_verbrauch", w.haus_verbrauch, 0);
        const hausverbrauch = document.getElementById("haus_verbrauch");
        if (hausverbrauch && finite_number(w.haus_verbrauch) !== null) {
            hausverbrauch.textContent += " W";
        }

        const relaySpan = document.getElementById("dose_relay_state");
        if (relaySpan) {
            if (w.dose_relay_state == null) {
                relaySpan.textContent = "OFFLINE";
                relaySpan.style.color = "gray";
            } else if (w.dose_relay_state === true) {
                relaySpan.textContent = "An";
                relaySpan.style.color = "red";
            } else {
                relaySpan.textContent = "Aus";
                relaySpan.style.color = "green";
            }
        }
        set_text("dose_mode", w.dose_mode === "auto" ? "Auto" : "Hand");
        set_mit_runden("dose_watt", w.dose_watt, 1);
        const doseWatt = document.getElementById("dose_watt");
        if (doseWatt && finite_number(w.dose_watt) !== null) {
            doseWatt.textContent += " Watt";
        }

        if (typeof akku.zeit_Noah === "string" &&
            akku.zeit_Noah !== lastNoahZeit) {
            const noahDate = new Date(akku.zeit_Noah.replace(" ", "T"));
            if (Number.isFinite(noahDate.getTime())) {
                lastNoahZeit = akku.zeit_Noah;
                zeitDiffMillis = Date.now() - noahDate.getTime();
                if (diffInterval) clearInterval(diffInterval);
                diffInterval = setInterval(() => {
                    set_text("zeit-diff", Math.floor(zeitDiffMillis / 1000));
                    zeitDiffMillis += 1000;
                }, 1000);
            }
        }
        set_text("akku-laden", akku.laden);
        set_text("akku-pac", akku.pac);
        set_text("akku-ppv", akku.ppv);
        set_mit_runden("akku-gesamt_t", akku.eacTotal, 1);
        set_text("daten_von", akku.daten_von);
        set_text("soc1", akku.soc1 == null ? "--" : `${akku.soc1}%`);
        set_text("soc2", akku.soc2 == null ? "--" : `${akku.soc2}%`);
        set_text(
            "dischargeSocLimit",
            akku.dischargeSocLimit == null
                ? "min⬇️ --"
                : `min⬇️ ${akku.dischargeSocLimit}%`
        );
        set_text(
            "chargeSocLimit",
            akku.chargeSocLimit == null
                ? "max⬆️ --"
                : `max⬆️ ${akku.chargeSocLimit}%`
        );
        set_text(
            "battery1Temp",
            akku.battery1Temp == null ? "--" : `${akku.battery1Temp}°C`
        );
        set_text(
            "battery2Temp",
            akku.battery2Temp == null ? "--" : `${akku.battery2Temp}°C`
        );
        set_text("battery1SerialNum", akku.battery1SerialNum);
        set_text("battery2SerialNum", akku.battery2SerialNum);
        set_text("ppv1", akku.ppv1 == null ? "--" : `${akku.ppv1}W`);
        set_text("ppv2", akku.ppv2 == null ? "--" : `${akku.ppv2}W`);
        const ppvTotal = Number(akku.ppv);
        const ppvOne = Number(akku.ppv1);
        const ppvTwo = Number(akku.ppv2);
        set_text(
            "ppv3",
            [akku.ppv, akku.ppv1, akku.ppv2].some(
                (value) => value === null || value === undefined || value === ""
            ) || ![ppvTotal, ppvOne, ppvTwo].every(Number.isFinite)
                ? "--"
                : `${ppvTotal - ppvOne - ppvTwo}W`
        );
        set_text("batteryCycles", akku.batteryCycles);

        const akkuStatus = document.getElementById("status");
        if (akkuStatus) {
            akkuStatus.textContent = akku.status === 1
                ? "Online"
                : akku.status == null ? "--" : `Status:${akku.status}`;
        }
        const socEl = document.getElementById("akku-soc");
        if (socEl) {
            socEl.textContent = akku.soc ?? "--";
            socEl.classList.remove(
                "bg-success", "bg-warning", "bg-danger", "text-white", "text-dark"
            );
            const soc = finite_number(akku.soc);
            if (soc !== null) {
                if (soc < 20) {
                    socEl.classList.add("bg-danger", "text-white");
                } else if (soc > 95) {
                    socEl.classList.add("bg-warning", "text-dark");
                } else {
                    socEl.classList.add("bg-success", "text-white");
                }
            }
        }
        set_text("akku-zeit", akku.zeit_meine?.slice(-8) || "--:--:--");

        const batteryTwoBlock = document.getElementById("battery2-block");
        if (batteryTwoBlock && akku.batteryZahl != null) {
            batteryTwoBlock.style.display = Number(akku.batteryZahl) === 1
                ? "none"
                : "flex";
        }

        set_text("hms-aktuel", hms.aktuell);
        set_mit_runden("hms-gesamt_t", hms.gesamt, 1);
        set_mit_runden("solax-gesamt_t", solax.gesamt, 1);
        const solaxPower = finite_number(s_l.aktuell);
        const cloudPower = finite_number(solax.acpower);
        set_text(
            "solax-actuel",
            solaxPower !== null && solaxPower > 0
                ? `L:${s_l.aktuell}`
                : cloudPower !== null && cloudPower > 0
                    ? `C:${solax.acpower}`
                    : "00"
        );

        const stromAktuell = document.getElementById("strom-aktuell");
        const currentPower = finite_number(strom.Actuel);
        if (stromAktuell) {
            stromAktuell.textContent = strom.Actuel ?? "--";
            stromAktuell.className = "px-2 py-1 rounded fw-bold";
            if (currentPower !== null) {
                stromAktuell.classList.add(
                    currentPower < 0
                        ? "bg-success"
                        : currentPower === 0 ? "bg-secondary" : "bg-danger",
                    "text-white"
                );
            }
        }
        set_mit_runden("strom-einspeise", strom.Einspeise, 1);
        set_mit_runden("strom-gesamt", strom.Gesamt, 1);
        set_text("strom-zeit", strom.zeit_meine?.slice(-8) || "--:--:--");

        set_mit_runden("tag-growatt", t.growatt_t, 3);
        set_mit_runden("tag-hms", t.hms_t, 3);
        set_mit_runden("tag-solax", t.solax_t, 3);
        set_mit_runden("tag-einspeise", t.einspeise_t, 3);
        set_mit_runden("tag-gesamt", t.gesamt_t, 3);

        const dailyValues = [t.solax_t, t.hms_t, t.einspeise_t].map(finite_number);
        const dailyEigenverbrauch = dailyValues.every(value => value !== null)
            ? dailyValues[0] + dailyValues[1] - dailyValues[2]
            : null;
        const liveValues = [solax.gesamt, hms.gesamt, strom.Einspeise].map(finite_number);
        const liveEigenverbrauch = liveValues.every(value => value !== null)
            ? liveValues[0] + liveValues[1] - liveValues[2]
            : null;
        set_mit_runden("solar-eigenverbrauch", liveEigenverbrauch, 1);
        set_mit_runden("tag-eigenverbrauch", dailyEigenverbrauch, 3);

        set_text("tag-tag", t.tag_t);
        aktualisiereAktuellAnzeige(e.aktuell_aktiv ?? true);
    } catch (err) {
        console.error("Fehler beim Laden der Daten:", err);
    }
}

function statusText(status) {
    switch (status) {
        case 0: return "⚪";
        case 1: return "🟢";
        case 2: return "🟡";
        case 3: return "🔴";
        default: return "⚪";
    }
}

const letzteDatenZeit = {};
function updateDatenAlter(data) {
    const daten = [
        { name: "akku_login", zeit: data.akku_login?.zeit_meine },
        { name: "akku", zeit: data.daten?.akku?.zeit_meine },
        { name: "hms", zeit: data.daten?.hms?.zeit_meine },
        { name: "solax-l", zeit: data.solax_local?.zeit_meine },
        { name: "solax-c", zeit: data.daten?.solax?.zeit_meine },
        { name: "dose", zeit: data.daten?.dose?.zeit_meine },
        { name: "strom", zeit: data.daten?.strom?.zeit_meine }
    ];
    daten.forEach(item => {
        if (item.zeit) {
            letzteDatenZeit[item.name] = item.zeit;
        }
    });
}

async function loop() {
    await ladeDaten();
    setTimeout(loop, interval);
}

loop();
