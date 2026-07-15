from fastapi import FastAPI, Request, Response 
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import asyncio
import json
import random

from aiomqtt import Client as MqttClient

from threading import Lock
import mysql.connector 

from pydantic import BaseModel

app = FastAPI(title="PV Cockpit Server")

# Jinja2-Template-Verzeichnis definieren
templates = Jinja2Templates(directory="templates")

# Binde den Ordner "static" unter dem Pfad "/static" ein
app.mount("/static", StaticFiles(directory="static"), name="static")

# 1. THREAD-SICHERHEIT: Lock initialisieren, falls andere Threads/Endgeräte
# gleichzeitig auf PV_LIVE_DATA zugreifen und Werte auslesen möchten.
PV_LIVE_DATA_LOCK = Lock()

# ersetzt im Zusammenhang mit opendtu, s.u.
# # ==========================================
# # CENTRAL STORAGE: Live-Daten im RAM
# # ==========================================
# PV_LIVE_DATA = {
#     "YieldActW": 0,
#     "YieldTotal": 0,

#     "PrognDay": 18.5,
#     "PrognDayRemain": 5.2,
    
#     "BattSoc": 0,
#     "BattRemainKwh": 0.0,
#     "BattInOutWload": 0,
#     "BattInOutAload": 0.0,
#     "BattInOutWconsum": 0,
#     "BattInOutAconsum": 0.0,
#     "BattV": 0.0,

#     "ShellyTotalKwh": 0,   # Gesamter Verbrauch im Haus in kWh
#     "ShellyCurrentWatts": 0 # Momentanverbrauch im Haus
# }

dSpeicherKapa = 10.0 # kWh

# Zentrales Mapping: Definiert Topic und Ziel-Key
TOPIC_MAPPING = {
   "solar/ac/yieldtotal": "YieldTotal",
   "solar/ac/power": "YieldActW",
   "solar/ac/yieldday": "YieldDay",
   "solar/ac/is_valid": "IsValid",
   "solar/dtu/temperature": "DtuTemp",
        
   # Wechselrichter 1
   "solar/116491433653/status/limit_absolute": "WR1_LimitAbs",
   "solar/116491433653/status/limit_relative": "WR1_LimitRel",
   "solar/116491433653/status/reachable": "WR1_Reachable",
   "solar/116491433653/0/power": "WR1_Power",
   "solar/116491433653/0/yieldday": "WR1_YieldDay",
   "solar/116491433653/0/yieldtotal": "WR1_YieldTotal",
   "solar/116491433653/0/temperature": "WR1_Temp",

   # Wechselrichter 2
   "solar/1164a00cbf56/status/limit_absolute": "WR2_LimitAbs",
   "solar/1164a00cbf56/status/limit_relative": "WR2_LimitRel",
   "solar/1164a00cbf56/0/power": "WR2_Power",
   "solar/1164a00cbf56/0/yieldday": "WR2_YieldDay",
   "solar/1164a00cbf56/0/yieldtotal": "WR2_YieldTotal",
   "solar/1164a00cbf56/0/temperature": "WR2_Temp",

   # Wechselrichter 3
   "solar/116492232746/status/limit_absolute": "WR3_LimitAbs",
   "solar/116492232746/status/limit_relative": "WR3_LimitRel",
   "solar/116492232746/0/power": "WR3_Power",
   "solar/116492232746/0/yieldday": "WR3_YieldDay",
   "solar/116492232746/0/yieldtotal": "WR3_YieldTotal",
   "solar/116492232746/0/temperature": "WR3_Temp"
}

PV_LIVE_DATA = {} # nimmt victron, shelly und opendtu-Werte auf

# ==========================================
# 1. FUNKTIONSHÜLLEN FÜR DIE DATENBESCHAFFUNG
# ==========================================

def hole_echte_pv_daten() -> dict:
   """
   Fallback-Funktion oder für API-Updates
   """
   with PV_LIVE_DATA_LOCK:
      return PV_LIVE_DATA

 # ==========================================
# 2. ROUTE FÜR DAS TABLET (ERSTAUFRUF)
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def cockpit_startseite(request: Request):
    # Geändert auf Ihr neues Template "pv_cockpit.html"
    #return templates.TemplateResponse("pv_cockpit.html", {"request": request, **PV_LIVE_DATA})
    return templates.TemplateResponse("limit.html", {"request": request, **PV_LIVE_DATA})

# ==========================================
# 3. ROUTE FÜR LIVE-UPDATES (POLLING VIA JS)
# ==========================================

@app.get("/api/pv-daten")
async def live_daten_api():
   with PV_LIVE_DATA_LOCK:
      return PV_LIVE_DATA.copy()

def update_pv_live_data(key, value):
    with PV_LIVE_DATA_LOCK:
        PV_LIVE_DATA[key] = value

# ==========================================
# BACKGROUND-TASK: REZEPTOR FÜR VICTRON MQTT
# ==========================================
async def victron_mqtt_listener():
    CERBO_IP = "192.168.2.38"  # Ihre reale Cerbo-IP laut Skript
    VRM_ID = "48e7da866373" # "216643"          # Ihre VRM-ID
    
    # Erweitertes Keep-Alive: Sagt dem Cerbo GX aktiv, dass wir Daten wollen
    async def send_keep_alive(client):
        # Beim ersten Start alle gewünschten IDs aktiv einmalig anfordern (Read-Befehl 'R/')
        themen = [
            f"R/{VRM_ID}/system/0/Dc/Battery/Soc",
            f"R/{VRM_ID}/system/0/Dc/Battery/Power",
            f"R/{VRM_ID}/system/0/Dc/Battery/Voltage",
            f"R/{VRM_ID}/system/0/Ac/Consumption/L1/Power",
            f"R/{VRM_ID}/system/0/Dc/Pv/Power"
        ]
        for t in themen:
            try:
                await client.publish(t, payload=None)
            except Exception:
                pass
                
        # Danach alle 40 Sekunden den globalen Lebenszyklus aufrechterhalten
        while True:
            try:
                await client.publish(f"R/{VRM_ID}/system/0/Serial", payload=None)
                await asyncio.sleep(40)
            except Exception:
                break

    while True:
        try:
            async with MqttClient(CERBO_IP) as client:
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Battery/Soc")
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Battery/Power")
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Battery/Voltage")
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Battery/Current")
                await client.subscribe(f"N/{VRM_ID}/system/0/Ac/Consumption/L1/Power")
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Pv/Power")
                
                asyncio.create_task(send_keep_alive(client))

                async for message in client.messages:
                    topic = str(message.topic)
                    #print(topic)
                    try:
                        payload_data = json.loads(message.payload.decode())
                        val = payload_data.get("value")
                        #print(val)

                        with PV_LIVE_DATA_LOCK:
                        
                           if val is not None:
                               if "Battery/Soc" in topic:
                                   PV_LIVE_DATA["BattSoc"] = int(val)
                                   PV_LIVE_DATA["BattRemainKwh"] = round((float(val) * dSpeicherKapa) / 100, 1)
                            
                               # beim Laden haben Watt und Amper positive Vorzeichen
                               elif "Battery/Power" in topic:
                                  if val > 0.0:
                                    PV_LIVE_DATA["BattInOutWload"] = int(val)
                                    PV_LIVE_DATA["BattInOutWconsum"] = 0
                                  else:
                                    PV_LIVE_DATA["BattInOutWload"] = 0
                                    PV_LIVE_DATA["BattInOutWconsum"] = int(val)

                               elif "Battery/Current" in topic:
                                   fVal = float(val)
                                   if fVal > 0.0:
                                    PV_LIVE_DATA["BattInOutAload"] = round(fVal, 1)
                                    PV_LIVE_DATA["BattInOutAconsum"] = 0
                                   else:
                                    PV_LIVE_DATA["BattInOutAload"] = 0
                                    PV_LIVE_DATA["BattInOutAconsum"] = round(fVal, 1)

                               elif "Battery/Voltage" in topic:
                                   PV_LIVE_DATA["BattV"] = round(float(val), 1)

                    except Exception:
                        pass
        except Exception as e:
            await asyncio.sleep(5)



# ==========================================
# NEU - BACKGROUND-TASK: REZEPTOR FÜR SHELLY MQTT
# ==========================================
async def shelly_mqtt_listener():
    """Lauscht auf dem lokalen Mosquitto-Broker des Raspberry Pi und fängt die JSON-Pakete des Shelly Pro EM 50 ab."""
    RASPI_IP = "192.168.2.28"  # IP vom Raspi (Mosquitto)
    SHELLY_ID = "shellyproem50-08f9e0e85934"

    while True:
        try:
            async with MqttClient(RASPI_IP) as client:
                await client.subscribe(f"{SHELLY_ID}/status/em1data:0")
                await client.subscribe(f"{SHELLY_ID}/status/em1data:1")
                await client.subscribe(f"{SHELLY_ID}/status/em1:0")
                await client.subscribe(f"{SHELLY_ID}/status/em1:1")

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        payload_dict = json.loads(message.payload.decode('utf-8'))
                        #print(payload_dict)

                        with PV_LIVE_DATA_LOCK:

                           if topic.endswith("status/em1data:1") and "total_act_ret_energy" in payload_dict:
                               PV_LIVE_DATA["ShellyTotalKwh"] = round(payload_dict["total_act_ret_energy"] / 1000.0, 0)

                           elif topic.endswith("status/em1:0") and "act_power" in payload_dict:
                               PV_LIVE_DATA["ShellyCurrentWatts"] = round(payload_dict["act_power"] * -1.0, 0)
                    except Exception: pass
        except Exception as e: 
           print(e)
           await asyncio.sleep(5)



# ==========================================
# NEU - BACKGROUND-TASK: REZEPTOR FÜR openDTU MQTT
# ==========================================
async def opendtu_mqtt_listener():
    """Lauscht auf dem lokalen Mosquitto-Broker des Raspberry Pi und fängt die JSON-Pakete de OpenDTU ab."""
    RASPI_IP = "192.168.2.28"  # IP vom Raspi (Mosquitto)
    SHELLY_ID = "OpenDTU-12920484"

    while True:
        try:
            async with MqttClient(RASPI_IP) as client:

                #await client.subscribe("solar/#")
                for topic in TOPIC_MAPPING.keys():
                    await client.subscribe(topic)
                 
                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        payload_dict = json.loads(message.payload.decode('utf-8'))
                        #print(f'openDTU: {topic}: {payload_dict}')

                        key_name = TOPIC_MAPPING[topic]
                        #print(f'openDTU: {key_name}: {topic}: {payload_dict}')
                            
                        if isinstance(payload_dict, (int, float)):
                           processed_value = round(payload_dict, 0)
                        else:
                           # Für Booleans (true/false) oder Strings (z.B. "reachable")
                           processed_value = payload_dict
                            
                        # Sicherer Schreibzugriff über das Lock
                        update_pv_live_data(key_name, processed_value)

                    except Exception: pass
        except Exception as e: 
           print(e)
           await asyncio.sleep(5)



# ==========================================
# NEU - BACKGROUND-TASK: PROGNOSE AUS MARIADB HOLEN
# ==========================================
async def mariadb_forecast_listener():
    """Liest regelmäßig die PV-Prognose aus der MariaDB und aktualisiert PV_LIVE_DATA."""
    while True:
        try:
            # Verbindung zur MariaDB aufbauen (Passe User, Passwort & DB-Name an!)
            conn = mysql.connector.connect(
                host="localhost",
                user="master",
                password="raspi",
                database="solar2023"
            )
            cursor = conn.cursor(dictionary=True)
            
            # Dein optimiertes SQL-Query (ohne die Gartenhaus-Einschränkung)
            query = """
            SELECT 
                ROUND(SUM(COALESCE(P1, P3, P6, P12, P24, 0)), 2) AS prognose_gesamt,
                ROUND(SUM(CASE 
                    WHEN Stunde >= NOW() THEN COALESCE(P1, P3, P6, P12, P24, 0) 
                    ELSE 0 
                END), 2) AS prognose_ab_jetzt
            FROM t_prognose
            WHERE DATE(Stunde) = CURDATE();
            """
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                # Werte in den zentralen RAM-Speicher schreiben
                PV_LIVE_DATA["PrognDay"] = result["prognose_gesamt"] if result["prognose_gesamt"] is not None else 0.0
                PV_LIVE_DATA["PrognDayRemain"] = result["prognose_ab_jetzt"] if result["prognose_ab_jetzt"] is not None else 0.0
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Fehler bei MariaDB-Abfrage: {e}")
            
        # Alle 15 Minuten (900 Sekunden) aktualisieren, da sich die Prognose selten ändert
        await asyncio.sleep(900)

# Startet alle MQTT-Listener
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(victron_mqtt_listener())
    asyncio.create_task(shelly_mqtt_listener())  # NEU
    asyncio.create_task(opendtu_mqtt_listener())  # NEU
    asyncio.create_task(mariadb_forecast_listener()) 




# ==========================================
# 4. DIE BUTTON-AKTIONEN
# ==========================================

MQTT_BROKER = "192.168.2.28"  # Deine Broker-IP
MQTT_PORT = 1883
INVERTERS = ["116491433653", "1164a00cbf56", "116492232746"]
MAX_TOTAL_LIMIT = 2000 

# Pydantic-Modell für die Datenvalidierung
class LimitRequest(BaseModel):
    limit: int

async def send_mqtt_limit(limit_per_inverter: float):
    """Baut eine asynchrone Verbindung auf und sendet die Limits an alle Inverter."""
    async with MqttClient(MQTT_BROKER, port=MQTT_PORT) as client:
        tasks = []
        for inverter in INVERTERS:
            #topic = f"solar/set/{inverter}/limit_absolute"
            #topic = f"solar/set/{inverter}/cmd/limit_persistent_absolute"
            topic = f"solar/{inverter}/cmd/limit_persistent_absolute"
            
            payload = str(int(limit_per_inverter))
            print(f"Sende per aiomqtt: {topic} -> {payload}W")
            # Füge das Veröffentlichen der Taskliste hinzu
            tasks.append(client.publish(topic, payload=payload, qos=1))
        
        # Sende alle MQTT-Befehle parallel ab
        await asyncio.gather(*tasks)

@app.post("/api/opendtu/set-limit")
async def set_limit(request_data: LimitRequest):
    try:
        #Nur für den Test der Fehlerbehandlung:
        # raise HTTPException(status_code=500, detail="Künstlicher MQTT-Verbindungsfehler im Test")
        # Statt raise HTTPException geben wir nun deine Struktur zurück
        # return {
        #     "status": "err2", 
        #     "text": f"Fehler bei der Verarbeitung: {str(request_data.limit)}W", 
        # }

        # TEST-ZEILE: Erzwinge sofort einen nackten HTTP 403 Fehler
        # return Response(status_code=403)

        total_limit = request_data.limit
        
        # Sicherheits-Check: Begrenzung auf das Maximum deiner Wechselrichter
        if total_limit > MAX_TOTAL_LIMIT:
            total_limit = MAX_TOTAL_LIMIT
        if total_limit < 0:
            total_limit = 0

        await send_mqtt_limit(total_limit)
            
        return {
            "status": "success", 
            "total_limit": total_limit, 
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/api/shelly/pruefen")
async def pruefe_shelly():
    return {"log": "Programmende shelly_check.py:\nShellyPro3 erfolgreich erreicht."}


