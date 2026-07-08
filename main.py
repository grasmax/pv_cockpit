from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import asyncio
import json
import random

from aiomqtt import Client as MqttClient

app = FastAPI(title="PV Cockpit Server")

# Jinja2-Template-Verzeichnis definieren
templates = Jinja2Templates(directory="templates")

# Binde den Ordner "static" unter dem Pfad "/static" ein
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# CENTRAL STORAGE: Live-Daten im RAM
# ==========================================
PV_LIVE_DATA = {
    "YieldActW": 0,
    "YieldTotal": 4512.3,

    "PrognDay": 18.5,
    "PrognDayRemain": 5.2,
    
    "BattSoc": 0,
    "BattRemainKwh": 0.0,
    "BattInOutWload": 0,
    "BattInOutAload": 0.0,
    "BattInOutWconsum": 0,
    "BattInOutAconsum": 0.0,
    "BattV": 0.0,
    
    "ConsumAct": 0
}

dSpeicherKapa = 10.0 # kWh

# ==========================================
# 1. FUNKTIONSHÜLLEN FÜR DIE DATENBESCHAFFUNG
# ==========================================

def hole_echte_pv_daten() -> dict:
    """
    Fallback-Funktion oder für API-Updates
    """
    return PV_LIVE_DATA

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
                    print(topic)
                    try:
                        payload_data = json.loads(message.payload.decode())
                        val = payload_data.get("value")
                        print(val)
                        
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

                            elif "Consumption" in topic:
                                PV_LIVE_DATA["ConsumAct"] = int(val)

                            elif "Dc/Pv/Power" in topic:
                                PV_LIVE_DATA["YieldActW"] = int(val)
                    except Exception:
                        pass
        except Exception as e:
            await asyncio.sleep(5)

# Startet den MQTT-Listener beim Hochfahren der FastAPI-App
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(victron_mqtt_listener())

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
    return PV_LIVE_DATA

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
                        if topic.endswith("status/em1data:1") and "total_act_ret_energy" in payload_dict:
                            PV_LIVE_DATA["ShellyTotalKwh"] = round(payload_dict["total_act_ret_energy"] / 1000.0, 0)

                        elif topic.endswith("status/em1:0") and "act_power" in payload_dict:
                            PV_LIVE_DATA["ShellyCurrentWatts"] = round(payload_dict["act_power"] * -1.0, 0)
                    except Exception: pass
        except Exception as e: 
           print(e)
           await asyncio.sleep(5)

# Startet beide MQTT-Listener
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(victron_mqtt_listener())
    asyncio.create_task(shelly_mqtt_listener())  # NEU



# ==========================================
# 4. FUNKTIONSHÜLLEN FÜR DIE BUTTON-AKTIONEN
# ==========================================

@app.post("/api/shelly/pruefen")
async def pruefe_shelly():
    return {"log": "Programmende shelly_check.py:\nShellyPro3 erfolgreich erreicht."}

@app.get("/api/opendtu/limits")
async def hole_opendtu_limits():
    return {"log": "Programmende opendtu_fetch.py:\nLimits ausgelesen."}

@app.post("/api/opendtu/set-limit")
async def setze_opendtu_limit(watt: int):
    return {"log": f"Programmende opendtu/opendtuhoylimit.py:\nLimit {watt} W gesendet."}
