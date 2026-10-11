from datetime import datetime
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent  # eine Ebene hoch zum Projektordner
DATA_DIR = BASE_DIR / "data"

STANDARD_ZUGANG= {
    #Growatt
    "token"	:   "",
    "deviceSn" :	"",
    "url_growatt_alle": "https://openapi.growatt.com/v4/new-api",

    "url_status": "https://openapi.growatt.com/noahDeviceApi/noah/getSystemStatus",
    "url_login" : "https://openapi.growatt.com/newTwoLoginAPI.do",
    "username"  : "",
    "password"  : "",

    "log_level": "INFO",
    
    "solax_c_url": "https://www.solaxcloud.com/proxyApp/proxy/api/getRealtimeInfo.do",
    "solax_c_tokenId": "",
    "solax_c_sn": "",
    "solax_l_url": "http://192.168.178.92",

    "ip_haupt": "http://192.168.178.",
    "ip_smart": "123", 
    "ip_tasmota": "42", 
    #"tasmota": "http://192.168.178.29/cm?cmnd=status%2010",
    "url_tasmota": "/cm?cmnd=status%2010",   

    "ip_hms": 44,
    "hms_name": "",
    "hms_pas": "",

    "ip_iobroker": 57,

    # Smart Dose – Zugangsdaten aus data/init_zugang.json
    "dose_device_id": "bfe769408c34e0dd06iuai",
    "dose_ip": "192.168.178.41",
    "dose_local_key": ""
}

STANDARD_EINSTELLUNGEN = {
    "server_sshd"    : False,

    "kochen_soc_min" : 40,
    "kochen_wert" : 1400,

    "solax_l_mittelwert_nutzen" : False,
    "nur_nulleinspeisung": False,
    "akku_entladen": False,  # soll akku max_limit entladen
    "akku_sanft": False,           # laden so das bis tagessende voll oder zeitinterval                  
    "akku_ppv": False,            #vole ppv leisung -mittel_verbrauch ins haus dazu
    "abfrage_tasmota": True,       # oder SML
    "abfrage_growatt": True,    # oder IoBrockerSML
    "hms_bekommt_null": False,    # für tasmota um verbrauch teuschen als 0
    "hms_limit_soll": 100,    # wenn hms_bekommt_null

    "max_limit": 800,              # was zun entladen bei soc voll
    "dazu_senden": 120,            #   jede 120 sek senden set_vdazu
    "dazu_sanft": 100,             # wenn zu  noch nicht voll aber sonne max für bestumte zeit
    "max_soc": 99,
    "ppv_soc_ab": 62,
    "mittel_verbrauch": 100,
    "einspeise_0":    0,
    "gesamt_0":    0,
    "hms_0":    0,
    "growatt_0":    0,
    "solax_0":    0,
    "tag_0": 0 , 
    "heute" :  datetime.now().strftime("%d.%m.%Y"),
    

    "monat_0": 0,
    "jahr_0": 0,

    "einspeise_monat_0": 0,
    "gesamt_monat_0": 0,
    "hms_monat_0": 0,
    "growatt_monat_0": 0,
    "solax_monat_0": 0,

    "einspeise_jahr_0": 0,
    "gesamt_jahr_0": 0,
    "hms_jahr_0": 0,
    "growatt_jahr_0": 0,
    "solax_jahr_0": 0,

    "intervall_takt": 4, # Sekunden  schleife zum actualisieren web ind zykl
    
    "takt_benutzrer_activ": 8,  #sek "intervall_takt"*2

    "aktuell_aktiv": True, ## 48

    "takt_hms": 8,
    "takt_akku": 60,
    "takt_akku_inactiv": 120,  
    "takt_solax_l": 9,
    "takt_solax_c": 300,
    "takt_cloud_nacht":600,
    "takt_strom": 10,
    "takt_dose": 300,
    
    "dose_t_start"    :31,
    "dose_t_stop"     :26
}
FELDREIHENFOLGE = [
    "datum",
    "tag_0",
    "einspeise_0",
    "gesamt_0",
    "hms_0",
    "growatt_0",
    "solax_0"
]

