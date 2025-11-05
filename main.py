from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Dictionnaires pour suivre les Arduinos et leurs commandes
arduinos_connected = {}
commands = {}

@app.get("/get_socket_bidirectionnel")
async def register_arduino(request: Request):
    """Appelé par l'Arduino au démarrage pour se déclarer"""
    arduino_name = request.query_params.get("arduino_name", "Unknown")
    client_ip = request.client.host
    arduinos_connected[arduino_name] = {"ip": client_ip}
    print(f"✅ Arduino connecté : {arduino_name} ({client_ip})")
    return JSONResponse({"status": "connected", "arduino": arduino_name})


@app.get("/get_arduino_connected")
async def get_connected():
    """Renvoie la liste des Arduinos enregistrés"""
    return JSONResponse(arduinos_connected)


@app.get("/set_command")
async def set_command(arduino: str, cmd: str):
    """Définit une commande (ex: REBOOT) à exécuter sur un Arduino"""
    commands[arduino] = cmd
    print(f"🛰️  Commande '{cmd}' envoyée à {arduino}")
    return JSONResponse({"status": "ok", "message": f"Commande '{cmd}' envoyée à {arduino}"})


@app.get("/get_command")
async def get_command(arduino: str):
    """Consulté par l'Arduino : renvoie la commande en attente"""
    cmd = commands.pop(arduino, None)
    if cmd:
        print(f"📤 Envoi de la commande '{cmd}' à {arduino}")
    return JSONResponse({"command": cmd or ""})


@app.get("/arduino_reboot")
async def reboot_arduino(arduino: str):
    """Envoie la commande REBOOT à un Arduino"""
    commands[arduino] = "REBOOT"
    print(f"♻️  Reboot demandé pour {arduino}")
    return JSONResponse({"status": "ok", "message": f"Reboot demandé pour {arduino}"})


@app.get("/")
async def index():
    """Simple page d’accueil"""
    return {"message": "Serveur Arduino opérationnel"}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
