from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio

app = FastAPI()

# Dictionnaires pour suivre les Arduinos et les ordres
arduinos_connected = {}   # {arduino_name: {"ip": str, "status": str}}
pending_commands = {}     # {arduino_name: "REBOOT"}

# Autoriser l’accès depuis ton navigateur (utile si tu appelles depuis un front)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/get_socket_bidirectionnel")
async def get_socket(request: Request):
    """
    Appelé par l’Arduino :
      - soit pour s’enregistrer
      - soit pour envoyer un "ping"
      - soit pour recevoir un ordre
    """
    arduino_name = request.headers.get("X-Arduino-Name", "Unknown")
    client_ip = request.client.host

    # Enregistre ou met à jour l'état de l'Arduino
    arduinos_connected[arduino_name] = {"ip": client_ip, "status": "connected"}

    print(f"📡 Requête reçue de {arduino_name} ({client_ip})")

    # Si une commande est en attente, on la renvoie et on la supprime
    if arduino_name in pending_commands:
        cmd = pending_commands.pop(arduino_name)
        print(f"➡️ Envoi de la commande '{cmd}' à {arduino_name}")
        return Response(content=cmd, media_type="text/plain")

    # Sinon, renvoie un simple message pour maintenir la connexion
    return Response(content="OK", media_type="text/plain")


@app.get("/get_arduino_connected")
async def get_connected():
    """Renvoie la liste des Arduinos connectés"""
    return JSONResponse(arduinos_connected)


@app.get("/arduino_reboot")
async def reboot_arduino(arduino: str):
    """
    Quand tu appelles :
      https://main1-n5uh.onrender.com/arduino_reboot?arduino=ArduinoSalon
    → le serveur stocke un ordre REBOOT pour cet Arduino
    """
    if arduino not in arduinos_connected:
        return JSONResponse({"status": "error", "message": "Arduino non connecté"})

    pending_commands[arduino] = "REBOOT"
    print(f"♻️ Reboot demandé pour {arduino}")
    return JSONResponse({"status": "ok", "message": f"Commande REBOOT envoyée à {arduino}"})


@app.get("/")
async def index():
    """Page d'accueil simple"""
    return {"status": "ok", "message": "Serveur Arduino en ligne"}


# Pour exécuter localement : python main.py
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
