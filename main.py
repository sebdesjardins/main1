# server.py
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connecté")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Reçu du client : {data}")
            # Renvoi un écho au client
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print("Client déconnecté")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render définit la variable PORT
    uvicorn.run("server:app", host="0.0.0.0", port=port)
