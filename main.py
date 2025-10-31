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
    print(f"📨 Message reçu : {msg}"
