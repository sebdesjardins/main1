from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import time

app = FastAPI()

# 🔹 Dictionnaire global : nom_arduino -> {"queue": ..., "last_seen": ...}
connected_arduinos = {}

@app.get("/get_socket_bidirectionnel")
async def get_socket_bidirectionnel(request: Request):
    """Connexion longue de l'Arduino (type streaming HTTPS)."""
    arduino_name = request.headers.get("x-arduino-name", "inconnu")
    print(f"✅ Nouvelle connexion depuis : {arduino_name}")

    queue = asyncio.Queue()
    connected_arduinos[arduino_name] = {
        "queue": queue,
        "last_seen": time.time()
    }

    async def event_stream():
        try:
            while True:
                # Vérifie si la connexion est encore ouverte
                if await request.is_disconnected():
                    print(f"❌ Déconnexion de {arduino_name}")
                    del connected_arduinos[arduino_name]
                    break

                # Tentative d'envoi d'une commande
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    # Keep-alive vide toutes les 10s
                    yield "\n"
                else:
                    yield f"{message}\n"

                # Mise à jour de l'activité
                connected_arduinos[arduino_name]["last_seen"] = time.time()

        except asyncio.CancelledError:
            print(f"Stream fermé pour {arduino_name}")

    return StreamingResponse(event_stream(), media_type="text/plain")


@app.post("/send/{arduino_name}")
async def send_command(arduino_name: str, request: Request):
    """
    Envoie une commande à un Arduino connecté.
    Exemple :
      POST /send/ArduinoSalon
      Body : "LED_ON"
    """
    if arduino_name not in connected_arduinos:
        return {"status": "erreur", "message": "Arduino non connecté"}

    data = await request.body()
    message = data.decode().strip()

    await connected_arduinos[arduino_name]["queue"].put(message)
    print(f"📤 Commande envoyée à {arduino_name} : {message}")

    return {"status": "ok", "envoyé": message}


@app.get("/get_arduino_connected")
async def get_arduino_connected():
    """
    Retourne la liste des Arduinos actuellement connectés.
    Exemple :
      GET /get_arduino_connected
    """
    result = {}
    now = time.time()

    for name, info in connected_arduinos.items():
        result[name] = {
            "connected": True,
            "last_seen_seconds_ago": round(now - info["last_seen"], 1)
        }

    return JSONResponse(result)


if __name__ == "__main__":
    import os, uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
