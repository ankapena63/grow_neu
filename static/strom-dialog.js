function zeigeGeraet(geraet) {
    let titel = "";
    let text = "";
    const d = aktuelleDaten?.daten;
    const t = aktuelleDaten?.tag_daten;
    const monat = aktuelleDaten?.monat_daten;
    const jahr = aktuelleDaten?.jahr_daten;
    const sLocal = aktuelleDaten?.solax_local;
    if (!d) {
        return;
    }
    // =========================
    // SOLAX
    // =========================
    if (geraet === "solax") {
        titel = "⚡ Solax";
        text = `
            <div class="text-start">
                <div class="d-flex justify-content-between">
                    <strong>Local:</strong>
                    <span>${sLocal?.aktuell ?? "--"} W</span>
                </div>

                <div class="d-flex justify-content-between">
                    <strong>Local: ⏱️</strong>
                    <span>${sLocal?.zeit_meine?.slice(-8) ?? "--:--:--"}</span>
                </div>

                <div class="d-flex justify-content-between">
                    <strong>Cloud:</strong>
                    <span>${d.solax?.acpower ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Upload: ☁️</strong>
                    <span>${d.solax?.upload_zeit?.slice(-8) ?? "--:--:--"}</span>
                </div>
               <div class="d-flex justify-content-between">
                    <strong>Abruf Zeit: ⏱️</strong>
                    <span>${d.solax?.zeit_meine?.slice(-8) ?? "--:--:--"}</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Heute:</strong>
                    <span>${t?.solax_t != null
                        ? Number(t.solax_t).toFixed(3)
                        : "--"} Wh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Monat:
                    ${monat?.monat!= null
                        ? Number(monat.monat).toFixed(0)
                        : "--"}</strong>
                    <span>${monat?.solax != null
                        ? Number(monat.solax).toFixed(1)
                        : "0.0"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Jahr:
                    ${jahr?.jahr!= null
                        ? Number(jahr.jahr).toFixed(0)
                        : "--"}</strong>
                    <span>${jahr?.solax != null
                        ? Number(jahr.solax).toFixed(1)
                        : "0.0"} kWh</span>
    
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Gesamt:</strong>
                    <span>${d.solax?.gesamt != null
                        ? Number(d.solax.gesamt).toFixed(1)
                        : "--"} kWh</span>
                </div>

                <div class="d-flex justify-content-between">
                    <strong>Takt:</strong>
                    <span>${d.solax?.takt ?? "--"} Sek</span>
                </div>
            </div>

        <pre class="text-start mb-0">${JSON.stringify(
            d.solax ?? {},
            null,
            2
        )}</pre>



        `;
    }
    // =========================
    // HMS
    // =========================
    if (geraet === "hms") {
        titel = "🔆 HMS-800";
        text = `
            <div class="text-start">
                <div class="d-flex justify-content-between">
                    <strong>Aktuell:</strong>
                    <span>${d.hms?.aktuell ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Limit:</strong>
                    <span>${d.hms?.limit ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Heute:</strong>
                    <span>${d.hms?.heute ?? "--"} Wh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Monat:
                    ${monat?.monat!= null
                        ? Number(monat.monat).toFixed(0)
                        : "--"}</strong>
                    <span>${monat?.hms != null
                        ? Number(monat.hms).toFixed(1)
                        : "0.0"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Jahr:
                    ${jahr?.jahr!= null
                        ? Number(jahr.jahr).toFixed(0)
                        : "--"}</strong>
                    <span>${jahr?.hms != null
                        ? Number(jahr.hms).toFixed(1)
                        : "0.0"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Gesamt:</strong>
                    <span>${d.hms?.gesamt != null
                        ? Number(d.hms.gesamt).toFixed(1)
                        : "--"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Ablese Zeit: ⏱️</strong>
                    <span>${d.hms?.zeit_meine?.slice(-8) ?? "--:--:--"}</span>
                </div>               
                <div class="d-flex justify-content-between">
                    <strong>Takt:</strong>
                    <span>${d.hms?.takt ?? "--"} Sek</span>
                </div>
            </div>


        <pre class="text-start mb-0">${JSON.stringify(
            d.hms ?? {},
            null,
            2
        )}</pre>
        `;
    }
    // =========================
    // STROM
    // =========================
    if (geraet === "strom") {
        titel = "⚡ Stromzähler";
        text = `

            <div class="text-start">
                <div class="d-flex justify-content-between">
                    <strong>Aktuell:</strong>
                    <span>${d.strom?.Actuel ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Zusatz:</strong>
                    <span>${d.strom?.vdazu ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Phase 1:</strong>
                    <span>${d.strom?.V1 ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Phase 2:</strong>
                    <span>${d.strom?.V2 ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Phase 3:</strong>
                    <span>${d.strom?.V3 ?? "--"} W</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Heute:</strong>
                    <span>${t?.gesamt_t != null
                        ? Number(t.gesamt_t*1000).toFixed(0)
                        : "--"} Wh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Monat:
                    ${monat?.monat!= null
                        ? Number(monat.monat).toFixed(0)
                        : "--"}</strong>
                    <span>${monat?.gesamt != null
                        ? Number(monat.gesamt).toFixed(1)
                        : "0.0"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Jahr:
                    ${jahr?.jahr!= null
                        ? Number(jahr.jahr).toFixed(0)
                        : "--"}</strong>
                    <span>${jahr?.gesamt != null
                        ? Number(jahr.gesamt).toFixed(1)
                        : "0.0"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Gesamt:</strong>
                    <span>${d.strom?.Gesamt != null
                        ? Number(d.strom.Gesamt).toFixed(1)
                        : "--"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Einspeisung:</strong>
                    <span>${d.strom?.Einspeise != null
                        ? Number(d.strom.Einspeise).toFixed(1)
                        : "--"} kWh</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Ablese Zeit: ⏱️</strong>
                    <span>${d.strom?.zeit_meine?.slice(-8) ?? "--:--:--"}</span>
                </div>
                <div class="d-flex justify-content-between">
                    <strong>Takt:</strong>
                    <span>${d.strom?.takt != null
                        ? Number(d.strom.takt).toFixed(0)
                        : "--"} Sek</span>
                </div>

            </div>      
        <pre class="text-start mb-0">${JSON.stringify(
            d.strom ?? {},
            null,
            2
        )}</pre>
        `;
    }
// =========================
    // STROM
    // =========================
    if (geraet === "akku") {
        titel = "⚡ Stromzähler";
        text = `
        <pre class="text-start mb-0">${JSON.stringify(
            d.akku ?? {},
            null,
            2
        )}</pre>
        `;
    }





    // =========================
    // MODAL ANZEIGEN
    // =========================
    document.getElementById("geraetModalTitel").textContent = titel;
    document.getElementById("geraetModalText").innerHTML = text;
    bootstrap.Modal
        .getOrCreateInstance(
            document.getElementById("geraetModal")
        )
        .show();
}
