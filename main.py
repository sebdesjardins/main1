from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Dictionnaire pour stocker les clients connectés
# key = MAC Arduino, value = socket id
clients = {}

@app.route('/')
def index():
    return "Serveur Arduino WebSocket actif"

# Route pour envoyer une commande pin à un Arduino
@app.route('/set_pin')
def set_pin():
    mac = request.args.get("mac")  # MAC obligatoire pour cibler un Arduino
    pin = request.args.get("pin")
    value_str = request.args.get("value", "HIGH").upper()

    if mac not in clients:
        return jsonify({"status": "error", "message": f"MAC {mac} non trouvé"}), 404

    if not pin:
        return jsonify({"status": "error", "message": "Paramètre 'pin' manquant"}), 400

    # Convertir value en 1/0
    value = 1 if value_str in ["HIGH", "1", "ON"] else 0

    data = {"pin": pin, "value": value}
    sid = clients[mac]
    socketio.emit("message", data, to=sid)

    return jsonify({"status": "ok", "pin": pin, "value": value, "mac": mac})

# Route pour lister toutes les MAC Arduino enregistrées
@app.route('/get_mc_address')
def get_mc_address():
    mac_list = list(clients.keys())
    return jsonify({"connected_mac": mac_list})

# WebSocket : connexion
@socketio.on('connect')
def handle_connect():
    print(f"✅ Client connecté, sid={request.sid}")

# WebSocket : réception messages de l'Arduino
@socketio.on('message')
def handle_message(data):
    print(f"Message reçu : {data}")
    import json
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
    # Supprimer le client de la liste
    remove_mac = [mac for mac, sid in clients.items() if sid == request.sid]
    for mac in remove_mac:
        print(f"Arduino déconnecté : {mac}")
        del clients[mac]

if __name__ == "__main__":
    # Pour Render, le port est généralement défini via env variable PORT
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
