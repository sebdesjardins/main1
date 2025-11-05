from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import asyncio

app = FastAPI()

# dictionnaire {nom_arduino: {"ws": websocket, "last_seen": datetime}}
connected_arduinos = {}

@app.websocket("/get_socket_bidirectionnel")
async def websocket_endpoint(websocket: WebSocket):
    # Accepter la connexion
    await websocket.accept()

    # Lire le nom de l’Arduino depuis le header HTTP
    arduino_name = websocket.headers.get("x-arduino-name", "UnknownArduino")

    connected_arduinos[arduino_name] = {"ws": websocket, "last_seen": datetime.now()}
    print(f"✅ Nouvelle connexion depuis : {arduino_name}")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"📩 {arduino_name} -> {data}")
            connected_arduinos[arduino_name]["last_seen"] = datetime.now()
    except Exception:
        print(f"⚠️ Arduino déconnecté : {arduino_name}")
    finally:
        connected_arduinos.pop(arduino_name, None)

@app.get("/get_arduino_connected")
async def get_connected():
    """Retourne la liste des Arduinos connectés avec leur dernier ping"""
    result = {}
    now = datetime.now()
    for name, info in connected_arduinos.items():
        delta = (now - info["last_seen"]).total_seconds()
        result[name] = {"connected": True, "last_seen_seconds_ago": delta}
    return JSONResponse(result)

@app.get("/arduino_reboot")
async def reboot_arduino(arduino: str):
    """Envoie une commande REBOOT à un Arduino connecté"""
    if arduino not in connected_arduinos:
        return JSONResponse({"status": "error", "message": "Arduino non connecté"}, status_code=404)
    try:
        ws = connected_arduinos[arduino]["ws"]
        await ws.send_text("REBOOT")
        return JSONResponse({"status": "ok", "message": f"Commande REBOOT envoyée à {arduino}"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import os, uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
