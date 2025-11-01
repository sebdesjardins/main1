from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import json
import os

app = Flask(__name__)
# Autoriser CORS pour tester depuis n'importe où
socketio = SocketIO(app, cors_allowed_origins="*")

# Dictionnaire pour stocker les clients Arduino connectés
# key = MAC, value = socket id
clients = {}

# Route test
@app.route('/')
def index():
    return "Serveur Arduino WebSocket actif"

# Route pour envoyer une commande pin à un Arduino
@app.route('/set_pin')
def set_pin():
    mac = request.args.get("mac")
    pin = request.args.get("pin")
    value_str = request.args.get("value", "HIGH").upper()

    if not mac or mac not in clients:
        return jsonify({"status": "error", "message": f"MAC {mac} non trouvé"}), 404
    if not pin:
        return jsonify({"status": "error", "message": "Paramètre 'pin' manquant"}), 400

    value = 1 if value_str in ["HIGH", "1", "ON"] else 0
    data = {"pin": pin, "value": value}
    sid = clients[mac]
    socketio.emit("message", data, to=sid)
    print(f"Commande envoyée à {mac} : {data}")
    return jsonify({"status": "ok", "pin": pin, "value": value, "mac": mac})

# Route pour lister toutes les MAC Arduino enregistrées
@app.route('/get_mc_address')
def get_mc_address():
    return jsonify({"connected_mac": list(clients.keys())})

# WebSocket : connexion d'un client
@socketio.on('connect')
def handle_connect():
    print(f"✅ Client WebSocket connecté, sid={request.sid}")

# WebSocket : réception d'un message (Arduino envoie sa MAC)
@socketio.on('message')
def handle_message(data):
    print(f"Message reçu : {data}")
    try:
        d = json.loads(data)
        if "mac" in d:
            mac = d["mac"]
            clients[mac] = request.sid
            print(f"Arduino enregistré avec MAC : {mac}")
            emit("message", "Connecté et enregistré sur le serveur !", to=request.sid)
    except Exception as e:
        print("Erreur JSON :", e)

# WebSocket : déconnexion
@socketio.on('disconnect')
def handle_disconnect():
    removed = [mac for mac, sid in clients.items() if sid == request.sid]
    for mac in removed:
        del clients[mac]
        print(f"Arduino déconnecté : {mac}")

if __name__ == "__main__":
    # Render définit le port via variable d'environnement PORT
    port = int(os.environ.get("PORT", 5000))
    print(f"Serveur lancé sur le port {port}")
    # allow_unsafe_werkzeug=True pour dev sur Render
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
