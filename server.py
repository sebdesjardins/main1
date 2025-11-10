from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY_CHANGE_ME"  # 🔑 Change cette clé

# -----------------------------
# CONFIG
# -----------------------------
SECURITY_KEY = "CLE1234"
ADMIN_PASSWORD = "admin123"
arduinos = {}  # { name: { 'last_seen': datetime, 'action': str, 'connected': bool } }
# Dictionnaire global pour stocker toutes les configs Arduino
arduinos_config = {}  # { "ARDUINO_EB20": { "name":..., "config_str":..., "pin_config": [...], "pin_value": [...] } }



# -----------------------------
# ROUTE POUR LES ARDUINOS
# -----------------------------
@app.route("/arduino", methods=["POST"])
def arduino_connect():
    data = request.get_json()
    if not data or data.get("key") != SECURITY_KEY:
        return jsonify({"status": "error", "message": "Invalid key"}), 403

    name = data.get("name", "unknown")
    now = datetime.utcnow()

    # Met à jour ou ajoute l’Arduino
    arduinos[name] = {
        "last_seen": now,
        "connected": True,
        "action": arduinos.get(name, {}).get("action", "")
    }

    # Récupère et vide l’action en attente
    action = arduinos[name]["action"]
    arduinos[name]["action"] = ""

    return jsonify({
        "status": "ok",
        "message": f"{name}, connexion OK.",
        "action": action
    })

# -----------------------------
# PAGE DE CONNEXION / LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))
        else:
            return render_template_string(LOGIN_HTML, error="Mot de passe incorrect.")
    return render_template_string(LOGIN_HTML)

LOGIN_HTML = """
<html>
<head>
    <title>Connexion</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f7f7f7; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .login-box { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); width: 300px; text-align: center; }
        input { padding: 10px; width: 90%; margin: 10px 0; }
        input[type=submit] { background: #0078D7; color: white; border: none; cursor: pointer; border-radius: 5px; }
        .error { color: red; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="login-box">
        <h3>🔐 Accès sécurisé</h3>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Mot de passe" required>
            <input type="submit" value="Se connecter">
        </form>
    </div>
</body>
</html>
"""

@app.route("/set_arduino_info", methods=["POST"])
def set_arduino_info():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Pas de données reçues"}), 400

        # Vérification de la clé de sécurité
        if data.get("key") != SECURITY_KEY:
            return jsonify({"status": "error", "message": "Clé invalide"}), 403

        name = data.get("name")
        if not name:
            return jsonify({"status": "error", "message": "Nom Arduino manquant"}), 400

        # Récupération des champs
        config_str = data.get("arduino_infos", "")  # ex : "ARDUINO_EB20;R4 Wifi;..."

        # Récupération des valeurs des broches
        pin_config_str = data.get("pin_config", "")
        pin_value_str = data.get("pin_value", "")

        # Conversion des strings en listes d'entiers
        pin_config = [int(x) for x in pin_config_str.split(";")] if pin_config_str else [0]*19
        pin_value = [int(x) for x in pin_value_str.split(";")] if pin_value_str else [0]*19

        # Mise à jour du dictionnaire global
        arduinos_config[name] = {
            "name": name,
            "config_str": config_str,
            "pin_config": pin_config,
            "pin_value": pin_value,
            "last_seen": datetime.utcnow()  # <- corrigé ici
        }

        print(f"Arduino {name} mis à jour : {arduinos_config[name]}")

        return jsonify({"status": "ok", "message": f"{name} configuration reçue et mise à jour."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# PAGE PRINCIPALE /HOME
# -----------------------------
@app.route("/home")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # Tableau des actions possibles
    arduinos_actions = ["reboot", "bonjour"]

    html = """
    <html>
    <head>
        <title>Arduino Monitor</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f7f7f7; margin: 20px; }
            table { border-collapse: collapse; width: 80%; background: white; box-shadow: 0 0 10px rgba(0,0,0,0.1); margin-bottom: 30px; }
            th, td { padding: 10px; text-align: center; border: 1px solid #ddd; }
            th { background-color: #0078D7; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .ok { color: green; font-weight: bold; }
            .off { color: red; font-weight: bold; }
            .logout { margin-top: 15px; }
            button { padding: 8px 16px; margin-top: 10px; cursor: pointer; border: none; background: #0078D7; color: white; border-radius: 5px; }
            button:hover { background: #005fa3; }
        </style>
        
        <script>
            // -----------------------------
            // Partie 1 : Tableau dynamique
            // -----------------------------
            async function refreshDynamicTable() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    const tableBody = document.getElementById('dynamic-table-body');
                    tableBody.innerHTML = '';
                    for (const [name, info] of Object.entries(data.arduinos)) {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${name}</td>
                            <td>${info.last_seen}</td>
                            <td class="${info.connected ? 'ok' : 'off'}">
                                ${info.connected ? '✅ Connecté' : '❌ Hors ligne'}
                            </td>
                            <td>${info.action || '(aucune)'}</td>
                        `;
                        tableBody.appendChild(row);
                    }
                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                } catch (err) {
                    console.error("Erreur AJAX:", err);
                }
            }
            setInterval(refreshDynamicTable, 3000);
            window.onload = refreshDynamicTable;
        </script>
    </head>
    <body>
        <h2>🛰️ Arduinos connus </h2>
        <p>Dernière actualisation : <span id="last-update">--:--:--</span></p>
        <table>
            <thead>
                <tr>
                    <th>Nom</th>
                    <th>Dernière connexion</th>
                    <th>Statut</th>
                    <th>Action actuelle</th>
                </tr>
            </thead>
            <tbody id="dynamic-table-body"></tbody>
        </table>

        <h2>🛠️ Envoi des actions vers les Arduinos</h2>
        <table>
            <thead>
                <tr>
                    <th>Nom</th>
                    <th>Envoyer Action</th>
                </tr>
            </thead>
            <tbody>
                {% for name, info in arduinos.items() %}
                <tr>
                    <td>{{ name }}</td>
                    <td>
                        <form method="POST" action="/set_action/{{ name }}">
                            <select name="action">
                                <option value="">Aucune</option>
                                {% for act in actions %}
                                <option value="{{ act }}">{{ act }}</option>
                                {% endfor %}
                            </select>
                            <input type="submit" value="Envoyer">
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <h2>📋 Informations détaillées des Arduinos connus</h2>

        {% for name, info in arduinos_config.items() %}
        {% set fields = info.config_str.split(';') %}
        <h3>🔧 Informations de {{ name }}</h3>
        <table>
            <thead>
                <tr>
                    <th>Nom du champ</th>
                    <th>Valeur</th>
                </tr>
            </thead>
            <tbody>
                <tr><td>Nom de l'Arduino</td><td>{{ fields[0] if fields|length > 0 else '' }}</td></tr>
                <tr><td>Type</td><td>{{ fields[1] if fields|length > 1 else '' }}</td></tr>
                <tr><td>Adresse IP</td><td>{{ fields[2] if fields|length > 2 else '' }}</td></tr>
                <tr><td>Mc Address</td><td>{{ fields[3] if fields|length > 3 else '' }}</td></tr>
                <tr><td>URL du serveur</td><td>https://{{ fields[4] if fields|length > 4 else '' }}</td></tr>
            </tbody>
        </table>
        {% endfor %}

        <div class="logout">
            <form action="/logout" method="POST">
                <input type="submit" value="🚪 Se déconnecter">
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, actions=arduinos_actions, arduinos=arduinos, arduinos_config=arduinos_config)



# -----------------------------
# ROUTE AJAX /STATUS
# -----------------------------
@app.route("/status")
def status():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 403

    now = datetime.utcnow()
    for name, info in arduinos.items():
        info["connected"] = (now - info["last_seen"]).total_seconds() <= 15

    data = {
        "arduinos": {
            name: {
                "last_seen": info["last_seen"].strftime("%H:%M:%S"),
                "connected": info["connected"],
                "action": info["action"]
            }
            for name, info in arduinos.items()
        }
    }
    return jsonify(data)

# -----------------------------
# ACTION MANUELLE
# -----------------------------
@app.route("/set_action/<name>", methods=["POST"])
def set_action(name):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    action = request.form.get("action", "")
    if name in arduinos:
        arduinos[name]["action"] = action
    return redirect(url_for("home"))
