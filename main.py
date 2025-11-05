from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse
from datetime import datetime

app = FastAPI()

# Dictionnaire pour suivre les Arduinos connectés
connected_arduinos = {}


@app.get("/get_socket_bidirectionnel")
async def http_fallback(request: Request):
    """Fallback HTTP pour Arduino UNO R4 WiFi"""
    arduino_name = request.headers.get("X-Arduino-Name", "UnknownArduino")
    connected_arduinos[arduino_name] = {"last_seen": datetime.now()}
    print(f"🔗 Connexion HTTP depuis : {arduino_name}")
    return JSONResponse({"status": "ok", "arduino": arduino_name})


@app.websocket("/get_socket_bidirectionnel")
async def websocket_endpoint(websocket: WebSocket):
    """Connexion WebSocket (pour cartes compatibles)"""
    await websocket.accept()
    arduino_name = websocket.headers.get("x-arduino-name", "UnknownArduino")
    connected_arduinos[arduino_name] = {"ws": websocket, "last_seen": datetime.now()}
    print(f"✅ Nouvelle connexion WS : {arduino_name}")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📩 {arduino_name} -> {data}")
            connected_arduinos[arduino_name]["last_seen"] = datetime.now()
    except Exception as e:
        print(f"⚠️ Déconnexion de {arduino_name} : {e}")
    finally:
        connected_arduinos.pop(arduino_name, None)


@app.get("/get_arduino_connected")
async def get_connected():
    """Retourne la liste des Arduinos connectés (HTTP ou WS)"""
    now = datetime.now()
    result = {}
    for name, info in connected_arduinos.items():
        delta = (now - info["last_seen"]).total_seconds()
        result[name] = {"connected": True, "last_seen_seconds_ago": delta}
    return JSONResponse(result)

commands = {}  # stocke les ordres en attente

@app.get("/set_command")
async def set_command(arduino: str, cmd: str):
    """Définit une commande à exécuter par l'Arduino"""
    commands[arduino] = cmd
    return {"status": "ok", "message": f"Commande '{cmd}' envoyée à {arduino}"}

@app.get("/get_command")
async def get_command(arduino: str):
    """Consultée par l'Arduino : renvoie la commande en attente"""
    cmd = commands.pop(arduino, None)
    return {"command": cmd or ""}

@app.get("/arduino_reboot")
async def reboot_arduino(arduino: str):
    """Envoie une commande REBOOT à l’Arduino"""
    if arduino not in connected_arduinos:
        return JSONResponse({"status": "error", "message": "Arduino non connecté"}, status_code=404)
    info = connected_arduinos[arduino]
    if "ws" not in info:
        # L’Arduino est connecté seulement en HTTP (pas de canal bidirectionnel)
        return JSONResponse({"status": "error", "message": "Arduino connecté en HTTP seulement"}, status_code=400)
    try:
        ws = info["ws"]
        await ws.send_text("REBOOT")
        print(f"🚀 Reboot demandé pour {arduino}")
        return JSONResponse({"status": "ok", "message": f"Commande REBOOT envoyée à {arduino}"})
    except Exception as e:
        print(f"❌ Erreur envoi REBOOT : {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
