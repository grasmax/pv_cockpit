from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import asyncio
import json
import random

from aiomqtt import Client as MqttClient

app = FastAPI(title="PV Cockpit Server")

# Jinja2-Template-Verzeichnis definieren
templates = Jinja2Templates(directory="templates")

# ==========================================
# CENTRAL STORAGE: Live-Daten im RAM
# ==========================================
VICTRON_LIVE_DATA = {
    "YieldActW": 0,
    "YieldTotal": 4512.3,
    "PrognDay": 18.5,
    "PrognDayRemain": 5.2,
    "BattSoc": 0,
    "BattRemainKwh": 0.0,
    "BattInOutW": 0,
    "BattInOutA": 0.0,
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
    return VICTRON_LIVE_DATA

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
                await client.subscribe(f"N/{VRM_ID}/system/0/Ac/Consumption/L1/Power")
                await client.subscribe(f"N/{VRM_ID}/system/0/Dc/Pv/Power")
                
                asyncio.create_task(send_keep_alive(client))

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        payload_data = json.loads(message.payload.decode())
                        val = payload_data.get("value")
                        
                        if val is not None:
                            if "Battery/Soc" in topic:
                                VICTRON_LIVE_DATA["BattSoc"] = int(val)
                                VICTRON_LIVE_DATA["BattRemainKwh"] = round((float(val) * dSpeicherKapa) / 100, 1)
                            elif "Battery/Power" in topic:
                                VICTRON_LIVE_DATA["BattInOutW"] = int(val)
                            elif "Battery/Voltage" in topic:
                                VICTRON_LIVE_DATA["BattV"] = round(float(val), 1)
                                if VICTRON_LIVE_DATA["BattV"] > 0:
                                    VICTRON_LIVE_DATA["BattInOutA"] = round(abs(VICTRON_LIVE_DATA["BattInOutW"]) / VICTRON_LIVE_DATA["BattV"], 1)
                            elif "Consumption" in topic:
                                VICTRON_LIVE_DATA["ConsumAct"] = int(val)
                            elif "Dc/Pv/Power" in topic:
                                VICTRON_LIVE_DATA["YieldActW"] = int(val)
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
    return templates.TemplateResponse("pv_cockpit.html", {"request": request, **VICTRON_LIVE_DATA})

# ==========================================
# 3. ROUTE FÜR LIVE-UPDATES (POLLING VIA JS)
# ==========================================

@app.get("/api/pv-daten")
async def live_daten_api():
    return VICTRON_LIVE_DATA

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
