#!/bin/bash
# 1. Verhindert, dass Android die CPU schlafen legt

# So machst du start.sh ausführbar:
# chmod +x start.sh
# starten ./start.sh

termux-wake-lock
# 2. In das Projektverzeichnis wechseln (Pfad anpassen!)
cd ~/storage/downloads/grow
# 3. Hypercorn starten
# --workers 1 ist wichtig, um Doppel-Tasks zu vermeiden

# Schreibt alle Ausgaben (auch Fehler) in solar.log
# '2>&1' sorgt dafÃ¼r, dass auch Fehlermeldungen im Log landen
#hypercorn neu:app --bind 0.0.0.0:5000 --workers 1 >> neu.log 2>&1

echo "--- Start Solar Monitor: $(date) ---" >>neu.log
hypercorn neu:app --bind 0.0.0.0:5000 --workers 1 2>&1 | tee -a neu.log

# 4. Falls das Programm beendet wird, Wake-Lock wieder freigeben
termux-wake-unlock