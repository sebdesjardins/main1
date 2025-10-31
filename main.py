from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Dictionnaire global pour stocker les Arduinos connectés
arduino_clients = {}

@app.route("/")
def home():
    """Page d'accueil simple pour vérifier l'état du serveur"""
    return jsonify({
        "status": "online",
        "connected_clients": list(arduino_clients.keys())
    })

@socketio.on("connect")
def on_connect():
    print("🔌 Nouveau client WebSocket connecté")

@socketio.on("disconnect")
def on_disconnect():
    # Retire l'Arduino s’il se déconnecte
    disconnected = None
    for mac, sid in list(arduino_clients.items()):
        if arduino_clients[mac] == request.sid:
            disconnected = mac
            del arduino_clients[mac]
    if disconnected:
        print(f"❌ Arduino {disconnected} déconnecté")
    else:
        print("Un client inconnu s’est déconnecté")

@socketio.on("message")
def handle_message(msg):
    """
    Gestion brute des messages venant de l'Arduino UNO R4
    car la lib WebSocketClient envoie tout via "message" (pas d'événements nommés).
    """
    print(f"📨 Message reçu : {msg}")
    try:
        import json
        data = json.loads(msg)
        event = data.get("event")
        payload = data.get("data", {})

        if event == "register":
            mac = payload.get("mac")
            if mac:
                arduino_clients[mac] = request.sid
                print(f"✅ Arduino enregistré : {mac}")
                emit("message", '{"event":"registered","data":{"status":"ok"}}')
        elif event == "pin_status":
            print(f"📩 Statut broche reçu : {payload}")
        else:
            print("⚠️ Événement inconnu :", event)
    except Exception as e:
        print(f"❌ Erreur de parsing JSON : {e}")

@app.route("/toggle_d2", methods=["POST"])
def toggle_d2():
    """
    Exemple de commande HTTP -> envoie une commande WebSocket à l’Arduino.
    JSON attendu : {"mac": "xx:xx:xx:xx:xx:xx"}
    """
    data = request.get_json()
    mac = data.get("mac")

    if mac not in arduino_clients:
        return jsonify({"error": "Arduino non connecté"}), 404

    sid = arduino_clients[mac]
    cmd = {"event": "toggle_pin", "data": {"pin": "D2", "state": "HIGH"}}

    import json
    socketio.emit("message", json.dumps(cmd), to=sid)
    print(f"📡 Commande toggle_pin envoyée à {mac}")
    return jsonify({"status": "sent", "mac": mac}), 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
