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

        # Récupération de l'adresse IP publique du client
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

        # Récupération des champs
        config_str = data.get("arduino_infos", "")  # ex : "ARDUINO_EB20;R4 Wifi;..."

        # Conversion des strings en listes d'entiers
        pin_config = [int(x) for x in pin_config_str.split(";")] if pin_config_str else [0]*19
        pin_value = [int(x) for x in pin_value_str.split(";")] if pin_value_str else [0]*19
        # Ajout de l'adresse IP à la fin de config_str
        if config_str:
            config_str += ";" + client_ip
        else:
            config_str = client_ip

        # Mise à jour du dictionnaire global
        arduinos_config[name] = {
            "name": name,
            "config_str": config_str,
            "pin_config": None,
            "pin_value": None,
            "last_seen": datetime.utcnow()  # <- corrigé ici
        }
        print(f"Arduino {name} mis à jour : {arduinos_config[name]}")
        return jsonify({"status": "ok", "message": f"{name} configuration reçue et mise à jour."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/set_arduino_config", methods=["POST"])
def set_arduino_config():
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

        # Récupération de l'adresse IP publique du client
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

        # Récupération de la chaîne contenant les deux tableaux concaténés
        config_str = data.get("arduino_config", "")  # ex: "10,0;20,0;15,1024;..."

        # Initialisation des tableaux
        pin_config = []
        pin_analog_value = []

        if config_str:
            broches = config_str.split(";")
            for b in broches:
                vals = b.split(",")
                if len(vals) == 2:
                    pin_config.append(int(vals[0]))
                    pin_analog_value.append(int(vals[1]))
                else:
                    pin_config.append(0)
                    pin_analog_value.append(0)
        else:
            pin_config = [0]*19
            pin_analog_value = [0]*19

        # Ajout de l'adresse IP à la fin de config_str
        if config_str:
            config_str += ";" + client_ip
        else:
            config_str = client_ip

        # Mise à jour du dictionnaire global
        arduinos_config[name]["name"] = name
        arduinos_config[name]["pin_config"] = pin_config
        arduinos_config[name]["pin_value"] = pin_analog_value
        arduinos_config[name]["last_seen"] = datetime.utcnow()


        print(f"Arduino {name} pin_config mis à jour : {arduinos_config[name]}")

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
            async function refreshConfigTable() {
                try {
                    const response = await fetch('/arduino_config_status');
                    const data = await response.json();
                    const container = document.getElementById('config-table-container');
                    container.innerHTML = '';
        
                    for (const [name, info] of Object.entries(data.arduinos_config)) {
                        const fields = info.config_str.split(';');
                        const ippub = (fields[5] || '').split(',');
        
                        const tableHTML = `
                            <h3>🔧 Informations de ${name}</h3>
                            <table>
                                <thead>
                                    <tr><th>Nom du champ</th><th>Valeur</th></tr>
                                </thead>
                                <tbody>
                                    <tr><td>Nom de l'Arduino</td><td>${fields[0] || ''}</td></tr>
                                    <tr><td>Type</td><td>${fields[1] || ''}</td></tr>
                                    <tr><td>Adresse IP locale</td><td>${fields[2] || ''}</td></tr>
                                    <tr><td>Mc Address</td><td>${fields[3] || ''}</td></tr>
                                    <tr><td>URL du serveur</td><td>https://${fields[4] || ''}</td></tr>
                                    <tr><td>Adresse IP publique</td><td>${ippub[0] || fields[5] || ''}</td></tr>
                                </tbody>
                            </table>
                        `;
                        container.innerHTML += tableHTML;
                    }
                } catch (err) {
                    console.error("Erreur AJAX (config):", err);
                }
            }
            setInterval(refreshDynamicTable, 3000);
            window.onload = function() {
                refreshDynamicTable();
                refreshConfigTable();
            };
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

        <div id="config-table-container"></div>

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
# PAGE SPECIFIQUE POUR UN ARDUINO /HOME_ARDUINO_CONFIG
# -----------------------------
@app.route("/home_arduino_config")
def home_arduino_config():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    arduino_name = request.args.get("arduino_name")
    if not arduino_name or arduino_name not in arduinos_config:
        return f"Erreur : Arduino '{arduino_name}' inconnu", 404
    html = """
    <html>
    <head>
        <title>Configuration {{ arduino_name }}</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f7f7f7; margin: 20px; }
            table { border-collapse: collapse; width: 90%; background: white; box-shadow: 0 0 10px rgba(0,0,0,0.1); margin-bottom: 30px; }
            th, td { padding: 8px; text-align: center; border: 1px solid #ddd; }
            th { background-color: #0078D7; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            h2, h3 { color: #0078D7; }
        </style>
        <script>
            async function refreshArduinoData() {
                try {
                    const response = await fetch('/arduino_config_status');
                    const data = await response.json();
                    const arduinoName = {{ arduino_name|tojson }};
                    const arduino = data.arduinos_config[arduinoName];
                    if (!arduino) return;
        
                    // --- Infos synthétiques ---
                    const fields = arduino.config_str.split(';');
                    const infoTableBody = document.getElementById('info-table-body');
                    infoTableBody.innerHTML = `
                        <tr><td>Nom de l'Arduino</td><td>${fields[0] || ''}</td></tr>
                        <tr><td>Type</td><td>${fields[1] || ''}</td></tr>
                        <tr><td>Adresse IP locale</td><td>${fields[2] || ''}</td></tr>
                        <tr><td>Mc Address</td><td>${fields[3] || ''}</td></tr>
                        <tr><td>URL du serveur</td><td>https://${fields[4] || ''}</td></tr>
                        <tr><td>Adresse IP publique</td><td>${fields[5] || ''}</td></tr>
                    `;       
                    // --- Tableau broches ---
                    const pinConfig = arduino.pin_config || [];
                    const pinValue = arduino.pin_value || [];
                    const pinNames = [];
                    for(let i=0;i<14;i++) pinNames.push("D"+i);
                    for(let i=0;i<6;i++) pinNames.push("A"+i);
        
                    const tableBody = document.getElementById('pins-table-body');
                    tableBody.innerHTML = '';
                    for(let i=0; i<19; i++){
                        const pc = pinConfig[i] || 0;
                        const bit0 = (pc >> 0) & 1;
                        const bit1 = (pc >> 1) & 1;
                        const bit2 = (pc >> 2) & 1;
                        const bit3 = (pc >> 3) & 1;
                        const bit4 = (pc >> 4) & 1;
                        const bit5 = (pc >> 5) & 1;       
                        const col_type = bit0  ? "DIGITALE" : "ANALOGIQUE";
                        const col_sortie_type = bit1 ? "DIGITALE" : "ANALOGIQUE";
                        const col_analog_out = bit2 ? "ANALOGIQUE" : "";
                        const col_used = bit3 ? "Réservée" : "Active";
                        const col_dir = bit4 ? "SORTIE" : "ENTREE";
                        let col_dig_val = bit5 ? "HIGH" : "LOW";
                        if(bit2==0 && pinValue[i]!==0 && pinValue[i]!==1024) col_dig_val = "";
                        const col_ana_val = bit2 ? pinValue[i] : "";       
                        const rowHTML = `
                            <tr>
                                <td>${i}</td>
                                <td>${pinNames[i]}</td>
                                <td>${col_type}</td>
                                <td>${col_sortie_type}</td>
                                <td>${col_analog_out}</td>
                                <td>${col_used}</td>
                                <td>${col_dir}</td>
                                <td>${col_dig_val}</td>
                                <td>${col_ana_val}</td>
                            </tr>
                        `;
                        tableBody.innerHTML += rowHTML;
                    }
                } catch(err){
                    console.error("Erreur AJAX:", err);
                }
            }        
            setInterval(refreshArduinoData, 3000);
            window.onload = refreshArduinoData;
        </script>
    </head>
    <body>
        <h2>🔧 Informations synthétiques de {{ arduino_name }}</h2>
        <table>
            <thead><tr><th>Nom du champ</th><th>Valeur</th></tr></thead>
            <tbody id="info-table-body"></tbody>
        </table>
        <h2>📊 Configuration détaillée des broches</h2>
        <table>
            <thead>
                <tr>
                    <th>No broche</th>
                    <th>Nom</th>
                    <th>Type</th>
                    <th>Type sortie</th>
                    <th>Sortie analogique</th>
                    <th>Broche utilisée</th>
                    <th>Entrée/Sortie</th>
                    <th>Valeur digitale</th>
                    <th>Valeur analogique</th>
                </tr>
            </thead>
            <tbody id="pins-table-body"></tbody>
        </table>
        <div class="logout">
            <form action="/logout" method="POST">
                <input type="submit" value="🚪 Se déconnecter">
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, arduino_name=arduino_name)


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
# ROUTE AJAX /arduino_config_status
# -----------------------------
@app.route("/arduino_config_status")
def arduino_config_status():
    data = {}
    for name, info in arduinos_config.items():
        data[name] = {
            "config_str": info.get("config_str", ""),
            "last_seen": info.get("last_seen", "")
        }
    return jsonify({"arduinos_config": data})

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
