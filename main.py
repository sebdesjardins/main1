# server.py
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

# Clé secrète partagée avec l'Arduino
SECURITY_KEY = "CLE1234"

# Base des arduinos
arduinos = {}  # { name: { 'last_seen': datetime, 'action': str, 'connected': bool } }

# Nettoyage automatique des arduinos inactifs
def cleanup_task():
    while True:
        now = datetime.utcnow()
        for name, info in list(arduinos.items()):
            if (now - info["last_seen"]).total_seconds() > 10:
                arduinos[name]["connected"] = False
        import time
        time.sleep(5)

threading.Thread(target=cleanup_task, daemon=True).start()

@app.route("/arduino", methods=["POST"])
def arduino_connect():
    data = request.get_json()
    if not data or data.get("key") != SECURITY_KEY:
        return jsonify({"status": "error", "message": "Invalid key"}), 403

    name = data.get("name", "unknown")
    now = datetime.utcnow()

    # Mettre à jour ou ajouter l'arduino
    if name not in arduinos:
        arduinos[name] = {"last_seen": now, "action": "", "connected": True}
    else:
        arduinos[name]["last_seen"] = now
        arduinos[name]["connected"] = True

    # Action à retourner à l'arduino
    action = arduinos[name]["action"]

    # Une fois envoyée, on efface l'action
    arduinos[name]["action"] = ""

    return jsonify({
        "status": "ok",
        "message": f"Bonjour {name}, connexion HTTPS réussie.",
        "action": action
    })

@app.route("/home")
def home():
    now = datetime.utcnow()
    html = """
    <html>
    <head><title>Arduino Monitor</title></head>
    <body>
        <h2>Liste des Arduinos connectés</h2>
        <table border="1" cellpadding="5">
            <tr><th>Nom</th><th>Dernière connexion</th><th>Statut</th><th>Action</th><th>Envoyer Action</th></tr>
            {% for name, info in arduinos.items() %}
            <tr>
                <td>{{ name }}</td>
                <td>{{ info.last_seen.strftime('%H:%M:%S') }}</td>
                <td>{{ "✅ Connecté" if info.connected else "❌ Hors ligne" }}</td>
                <td>{{ info.action or "(aucune)" }}</td>
                <td>
                    <form method="POST" action="/set_action/{{ name }}">
                        <select name="action">
                            <option value="">Aucune</option>
                            <option value="conexion_https_ok()">conexion_https_ok()</option>
                        </select>
                        <input type="submit" value="Envoyer">
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, arduinos=arduinos)

@app.route("/set_action/<name>", methods=["POST"])
def set_action(name):
    action = request.form.get("action", "")
    if name in arduinos:
        arduinos[name]["action"] = action
    return ("<meta http-equiv='refresh' content='0; url=/home'>")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
