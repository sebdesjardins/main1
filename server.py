from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from datetime import datetime
from app_meteo import *
import time
import threading
import json
import os
import copy
from pprint import pprint

#PERSIST_FILE = "/var/data/meteo.json"
#if not os.path.isdir("/var/data"):
#    PERSIST_FILE = "./meteo.json"
PERSIST_FILE = "./meteo.json"

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
# Modèle global indépendant de toute carte
APP_MODEL = {
    "arrosage": {
        "b": {
            "forcage_pompe1_active": 0,
            "forcage_pompe2_active": 0,
            "forcage_pompe3_active": 0,
            "forcage_pompe4_active": 0,
            "mode_automatique": 0
        },
        "i": {},
        "s": {}
    },
    "meteo": {
        "i": {
            "city_number" : "6"
        },
        "s": {
            "city_name_1": "",
            "city_meteo_1": "",
            "city_name_2": "",
            "city_meteo_2": "",
            "city_name_3": "",
            "city_meteo_3": "",
            "city_name_4": "",
            "city_meteo_4": "",
            "city_name_5": "",
            "city_meteo_5": "",
            "city_name_6": "",
            "city_meteo_6": "",
            "city_name_7": "",
            "city_meteo_7": "",
            "city_name_8": "",
            "city_meteo_8": "",
            "city_name_9": "",
            "city_meteo_9": "",
        },
        "b": {}
    }
}

def update_app_meteo():
    global APP_MODEL
    from app_meteo import cities, update_city_meteo
    city_number = int(APP_MODEL["meteo"]["i"]["city_number"])
    for i in range(0, city_number ):
        # Mise à jour météo de la ville itmp_var
        # Injection résultats dans le APP_MODEL
        APP_MODEL["meteo"]["s"][f"city_name_{i}"]  = cities[i-1]["name"]
        tmp_var = cities[i-1]["meteo"].replace("&deg;", "")
        print(f':update_app_meteo : tmp_var={tmp_var}')
        APP_MODEL["meteo"]["s"][f"city_meteo_{i}"] = tmp_var
    path = PERSIST_FILE
    if not os.path.exists(path):
        print(f'Fonction update_app_meteo() : bkp structure vide')
        print(f">>> Création du fichier {PERSIST_FILE}")
        with open(PERSIST_FILE, "w", encoding="utf-8") as f:
            json.dump(APP_MODEL, f, ensure_ascii=False, indent=2)
        return {}
    with open(PERSIST_FILE, "r", encoding="utf-8") as f:
        APP_MODEL = json.load(f)

# --- route de mise à jour complète ---
@app.route("/update_meteo")
def update_meteo():
    """
    Met à jour la météo de toutes les villes présentes dans APP_MODEL['meteo'].
    Utilise load_persist() pour s'assurer qu'on part des données sauvegardées.
    """
    global APP_MODEL

    # 1) forcer rechargement du persist pour être sûr d'être synchronisé
    load_persist()

    city_number = int(APP_MODEL["meteo"]["i"]["city_number"])
    print(f"[update_meteo] city_number={city_number}")

    for idx in range(1, city_number + 1):
        name = APP_MODEL["meteo"]["s"].get(f"city_name_{idx}", "").strip()
        print(f"[update_meteo] idx={idx} name='{name}'")
        if not name:
            APP_MODEL["meteo"]["s"][f"city_meteo_{idx}"] = ""
            continue

        try:
            forecast = get_forecast_for_city(name).replace("&deg;", "")
            APP_MODEL["meteo"]["s"][f"city_meteo_{idx}"] = forecast
            print(f"[update_meteo] -> forecast length={len(forecast)}")
        except Exception as e:
            print("[update_meteo] Erreur fetch:", e)
            APP_MODEL["meteo"]["s"][f"city_meteo_{idx}"] = ""

    # 2) sauvegarde et retour à la page
    save_persist()
    # 3) envoyer l'ordre de raffraichissement de la météo aux arduinos
    for name, ar in arduinos.items():
        ar["actions"].append("refresh_meteo")

    return redirect("/meteo")


def meteo_background_task():
    while True:
        try:
            print("[METEO] Mise à jour automatique...")
            update_app_meteo()
        except Exception as e:
            print("Erreur update_app_meteo:", e)
        time.sleep(300)  # 300 sec = 5 minutes



# -----------------------------
# ROUTE POUR ENVOYER UNE VARIABLE DE L'ARDUINOS
# -----------------------------
@app.route("/arduino_vars", methods=["POST"])
def arduino_vars():
    data = request.get_json(force=True)
    key  = data.get("key", "")
    name = data.get("name", "")
    var  = data.get("var", "")  # string "nom=valeur"
    if key != SECURITY_KEY:
        return "Forbidden", 403
    if "=" in var:
        nom, valeur = var.split("=", 1)
        if name not in arduinos:
            arduinos[name] = {"vars": { "arrosage": {} }, "srv_queue": []}
        # Extraire le nom de l'application
        app_name = nom.split(".")[0]  # ex: "arrosage.i.secheresse_pot1" -> "arrosage"
        if "vars" not in arduinos[name]:
            arduinos[name]["vars"] = {}
        if app_name not in arduinos[name]["vars"]:
            arduinos[name]["vars"][app_name] = {}
        arduinos[name]["vars"][app_name][nom] = valeur
        print("RECEPTION VARIABLE DE L'ARDUINO : APPLICATION="+app_name+"  NOM_VARIABLE=" + nom + "  VALEUR=" + valeur + "\n")

    return "OK"



def init_srv_variables_for_arduino(name):
    if "variables_srv" not in arduinos[name] or not arduinos[name]["variables_srv"]:
        arduinos[name]["variables_srv"] = copy.deepcopy(APP_MODEL)
        print(f"[INIT] Variables serveur initialisées pour {name}")


# -----------------------------
# ROUTE POUR LES ARDUINOS (connexion principale)
# -----------------------------
@app.route("/arduino", methods=["POST"])
def arduino_connect():
    data = request.get_json()
    if not data or data.get("key") != SECURITY_KEY:
        return jsonify({"status": "error", "message": "Invalid key"}), 403
    name = data.get("name", "unknown")
    now = datetime.utcnow()
    # Assure l'existence de l'entrée et de la file d'actions
    # Première connexion ?
    if name not in arduinos:
        arduinos[name] = {
            "connected": True,
            "last_seen": datetime.now(),
            "vars": {},
            "variables_srv": {},
            "action":{},
            "srv_queue": []
        }
        init_srv_variables_for_arduino(name)
        print(f"[INFO] Arduino {name} ajouté avec modèle variables_srv.")
    else:
        # met à jour timestamp / connexion sans écraser la file d'actions
        arduinos[name].setdefault("actions", [])
        arduinos[name]["last_seen"] = now
        arduinos[name]["connected"] = True
        # En cas de reset de l’arduino, s’assurer du modèle
        if "variables_srv" not in arduinos[name] or not arduinos[name]["variables_srv"]:
            init_srv_variables_for_arduino(name)
    # Récupère la première action en FIFO (si présente) et la retire de la file
    action_to_send = ""
    if isinstance(arduinos[name].get("actions"), list) and len(arduinos[name]["actions"]) > 0:
        action_to_send = arduinos[name]["actions"].pop(0)
    # Log pour debug
    print(f"Arduino {name} connecté à {now}. Action envoyée: {action_to_send or 'aucune'}")
    print(f"Actions restantes: {arduinos[name].get('actions', [])}")
    return jsonify({
        "status": "ok",
        "message": f"{name}, connexion OK.",
        "action": action_to_send
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
        infos_str = data.get("arduino_infos", "")  # ex : "ARDUINO_EB20;R4 Wifi;..."
        # Récupération des valeurs des broches
        pin_config_str = data.get("pin_config", "")
        pin_value_str = data.get("pin_value", "")
        # Conversion des strings en listes d'entiers
        pin_config = [int(x) for x in pin_config_str.split(";")] if pin_config_str else [0]*19
        pin_value = [int(x) for x in pin_value_str.split(";")] if pin_value_str else [0]*19
        # Ajout de l'adresse IP à la fin de config_str
        if infos_str:
            infos_str += ";" + client_ip
        else:
            infos_str = client_ip
        # Mise à jour du dictionnaire global
        arduinos_config[name] = {
            "name": name,
            "info_str": infos_str,
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
    arduinos_actions = ["reboot", "bonjour","refresh_meteo"]
    # Liste des applications disponibles d'après APP_MODEL
    app_names = list(APP_MODEL.keys())
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
            button:hover { background-color: #005fa3; }
            .link-config { margin-top: 5px; display: block; }
        </style>
        <script>
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
            async function refreshInfoTable() {
                try {
                    const response = await fetch('/arduino_infos_status');
                    const data = await response.json();
                    const container = document.getElementById('info-table-container');
                    container.innerHTML = '';
                    for (const [name, info] of Object.entries(data.arduinos_info)) {
                        const fields = info.infos_str.split(';');
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
                            <a class="link-config" href="/home_arduino_config?arduino_name=${name}">➡️ Voir la configuration détaillée</a>
                        `;
                        container.innerHTML += tableHTML;
                    }
                } catch (err) {
                    console.error("Erreur AJAX (infos):", err);
                }
            }
            setInterval(refreshDynamicTable, 3000);
            setInterval(refreshInfoTable, 5000);
            window.onload = function() {
                refreshDynamicTable();
                refreshInfoTable();
            };
        </script>
    </head>
    <body>
        <!-- Nouvelle section : Applications disponibles -->
        <h2>📱 Applications disponibles</h2>
        <table>
            <thead>
                <tr>
                    <th>Nom de l'application</th>
                    <th>Accès</th>
                </tr>
            </thead>
            <tbody>
                {% for app in app_names %}
                <tr>
                    <td>{{ app }}</td>
                    <td><a href="/{{ app }}">➡️ Aller à {{ app }}</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <!-- Section existante : Arduinos connus -->
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
        <div id="info-table-container"></div>

        <div class="logout">
            <form action="/logout" method="POST">
                <input type="submit" value="🚪 Se déconnecter">
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, actions=arduinos_actions, arduinos=arduinos, app_names=app_names)

# -----------------------------
# PAGE /HOME_ARDUINO_CONFIG
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
            body { font-family: Arial, sans-serif; background: #f7f7f7; margin: 20px; }
            table { border-collapse: collapse; width: 95%; background: white; box-shadow: 0 0 10px rgba(0,0,0,0.1); margin-bottom: 18px; }
            th, td { padding: 8px; text-align: center; border: 1px solid #ddd; }
            th { background-color: #0078D7; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .gray-cell { background-color: #d3d3d3; color: #666; }
            h2 { color: #0078D7; }
            a.link-config { text-decoration: none; color: #0078D7; font-weight: bold; }
            a.link-config:hover { text-decoration: underline; }
            input[type=range] { width: 100px; }
            button { padding: 4px 8px; margin: 2px; }
        </style>
        <script>
            async function refreshArduinoData() {
                try {
                    const response = await fetch('/arduino_config_status');
                    const data = await response.json();
                    const arduinoName = {{ arduino_name|tojson }};
                    const arduino = data.arduinos_info[arduinoName];
                    if (!arduino) return;
                    const pinConfig = Array.isArray(arduino.pin_config) ? arduino.pin_config : [];
                    const pinValue  = Array.isArray(arduino.pin_value)  ? arduino.pin_value  : [];
                    const pinNames = [];
                    for (let i = 0; i < 14; i++) pinNames.push("D" + i);
                    for (let i = 0; i < 6;  i++) pinNames.push("A" + i);
                    const pwmPins = ["D3","D5","D6","D9","D10","D11"];
                    const tableBody = document.getElementById('pins-table-body');
                    tableBody.innerHTML = '';
                    const maxLen = Math.max(pinNames.length, pinConfig.length, pinValue.length);
                    for (let i = 0; i < maxLen; i++) {
                        const name = pinNames[i] ?? ("A" + (i - 14));
                        const pc = Number(pinConfig[i] ?? 0);
                        const rawVal = pinValue[i];
                        const valNum = (rawVal === null || rawVal === "" || rawVal === undefined) ? 0 : Number(rawVal);
                        const bit1 = (pc >> 1) & 1;
                        const bit3 = (pc >> 3) & 1; // reserved
                        const bit4 = (pc >> 4) & 1;
                        const reserved = (bit3 === 1);
                        const isDigitalPinName = (i < 14);
                        const pinType = isDigitalPinName ? "DIGITALE" : "ANALOGIQUE";
                        const canPWM = pwmPins.includes(name) ? "PWM" : "";
                        const usedAs = bit1 ? "DIGITALE" : "ANALOGIQUE";
                        const used = reserved ? "" : "Active";
                        const direction = reserved ? "" : (bit4 ? "SORTIE" : "ENTRÉE");
                        let digVal = "";
                        let anaVal = "";
                        if (!reserved && !isNaN(valNum)) {
                            if (valNum === 0) digVal = "LOW";
                            else if (valNum === 255) digVal = "HIGH";
                            anaVal = valNum;
                        }
                        // ================================
                        // CHOIX DU COMPOSANT DE CONTROLE
                        // ================================
                        let controlHTML = "";
                        if (!reserved && bit4 === 1) {
                            if (bit1 === 1) {
                                // -------- DIGITAL OUTPUT --------
                                const label = (valNum === 0) ? "HIGH" : "LOW";
                                const newValue = (valNum === 0) ? 255 : 0;

                                controlHTML = `
                                    <button onclick="sendPinValue(${i}, ${newValue})">
                                        ${label}
                                    </button>`;
                            }
                            else {
                                // -------- ANALOG OUTPUT --------
                                controlHTML = `
                                    <input type="range" min="0" max="255" value="${valNum}"
                                        id="slider-${i}"
                                        onchange="sendSlider(${i})">`;
                            }
                        }
                        const controlCellClass = reserved ? "gray-cell" : "";
                        const rowHTML = `
                            <tr>
                                <td>${i}</td>
                                <td>${name}</td>
                                <td>${pinType}</td>
                                <td>${canPWM}</td>
                                <td>${usedAs}</td>
                                <td class="${reserved ? 'gray-cell' : ''}">${used}</td>
                                <td class="${reserved ? 'gray-cell' : ''}">${direction}</td>
                                <td class="${reserved ? 'gray-cell' : ''}">${digVal}</td>
                                <td class="${reserved ? 'gray-cell' : ''}">${anaVal}</td>
                                <td class="${controlCellClass}">${controlHTML}</td>
                            </tr>
                        `;
                        tableBody.innerHTML += rowHTML;
                    }
                } catch (err) {
                    console.error("Erreur AJAX:", err);
                }
            }
            async function sendPinValue(pin, value) {
                const arduinoName = {{ arduino_name|tojson }};
                try {
                    await fetch('/update_pin_value', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            key: "{{ SECURITY_KEY }}",
                            name: arduinoName,
                            pin: pin,
                            value: Number(value)
                        })
                    });
                } catch (err) {
                    console.error("Erreur digital:", err);
                }
            }
            async function sendSlider(pin) {
                const slider = document.getElementById("slider-" + pin);
                if (!slider) return;
                const value = Number(slider.value);
                const arduinoName = {{ arduino_name|tojson }};
                try {
                    await fetch('/update_pin_value', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            key: "{{ SECURITY_KEY }}",
                            name: arduinoName,
                            pin: pin,
                            value: value
                        })
                    });
                } catch (err) {
                    console.error("Erreur slider:", err);
                }
            }
            setInterval(refreshArduinoData, 3000);
            window.onload = refreshArduinoData;
        </script>
    </head>
    <body>
        <h2>🔧 Informations synthétiques de {{ arduino_name }}</h2>
        <h2>📊 Configuration détaillée des broches</h2>
        <table>
            <thead>
                <tr>
                    <th>No</th>
                    <th>Nom</th>
                    <th>Type</th>
                    <th>PWM possible</th>
                    <th>Broche utilisée comme</th>
                    <th>Broche utilisée</th>
                    <th>Entrée / Sortie</th>
                    <th>Valeur digitale</th>
                    <th>Valeur analogique</th>
                    <th>Contrôle</th>
                </tr>
            </thead>
            <tbody id="pins-table-body"></tbody>
        </table>
        <a class="link-config" href="/home">➡️ Retour</a>
    </body>
    </html>
    """
    return render_template_string(html, arduino_name=arduino_name, SECURITY_KEY=SECURITY_KEY)

# -----------------------------
# ROUTE/UPDATE_PIN_VALUE
# -----------------------------
@app.route("/update_pin_value", methods=["POST"])
def update_pin_value():
    if not session.get("logged_in"):
        return jsonify({"status": "error", "message": "non autorisé"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Pas de données reçues"}), 400
    # Vérification clé de sécurité
    if data.get("key") != SECURITY_KEY:
        return jsonify({"status": "error", "message": "Clé invalide"}), 403
    name = data.get("name")
    pin = data.get("pin")
    value = data.get("value")
    if name not in arduinos_config:
        return jsonify({"status": "error", "message": f"Arduino '{name}' inconnu"}), 404
    try:
        pin = int(pin)
        value = int(value)
    except Exception:
        return jsonify({"status": "error", "message": "Pin ou valeur invalide"}), 400
    # Clamp valeur 0..255
    if value < 0:
        value = 0
    if value > 255:
        value = 255
    # Mettre à jour la valeur côté serveur (assure existencia du tableau)
    if arduinos_config[name].get("pin_value") is None or not isinstance(arduinos_config[name]["pin_value"], list):
        arduinos_config[name]["pin_value"] = [0] * 20
    if 0 <= pin < len(arduinos_config[name]["pin_value"]):
        arduinos_config[name]["pin_value"][pin] = value
    else:
        return jsonify({"status": "error", "message": "Numéro de broche hors limite"}), 400
    # Préparer l'action pour l'Arduino (en FIFO)
    action_cmd = f"/set_arduino_pin_value?pin={pin}&value={value}"
    # Assure l'existence de la structure d'actions côté runtime (arduinos)
    if name not in arduinos:
        arduinos[name] = {"last_seen": datetime.utcnow(), "connected": False, "actions": []}
    if "actions" not in arduinos[name] or not isinstance(arduinos[name]["actions"], list):
        arduinos[name]["actions"] = []
    # Ajoute en fin de file (FIFO)
    arduinos[name]["actions"].append(action_cmd)
    print(f"Action ajoutée à la file pour {name}: {action_cmd}")
    print(f"File maintenant: {arduinos[name]['actions']}")
    return jsonify({"status": "ok", "message": f"Valeur broche {pin} mise à jour", "action_queued": action_cmd})


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
                "action": info["actions"]
            }
            for name, info in arduinos.items()
        }
    }
    return jsonify(data)

# -----------------------------
# ROUTE AJAX /arduino_infos_status
# -----------------------------
@app.route("/arduino_infos_status")
def arduino_infos_status():
    data = {}
    for name, info in arduinos_config.items():  # <-- garder arduinos_config
        data[name] = {
            "infos_str": info.get("info_str", ""),  # <-- info_str et non config_str
            "last_seen": info.get("last_seen", "")
        }
    return jsonify({"arduinos_info": data})  # <-- clé JSON peut rester arduinos_info

# -----------------------------
# ROUTE AJAX /arduino_config_status
# -----------------------------
@app.route("/arduino_config_status")
def arduino_config_status():
    data = {}
    for name, info in arduinos_config.items():  # On garde le stockage côté serveur dans arduinos_config
        data[name] = {
            "infos_str": info.get("info_str", ""),      # Infos synthétiques de l'Arduino
            "pin_config": info.get("pin_config", []),  # Tableau des broches
            "pin_value": info.get("pin_value", []),    # Valeurs analogiques/digitales
            "last_seen": info.get("last_seen", "")
        }
    # La clé JSON renvoyée côté JS sera "arduinos_info" pour rester cohérent
    return jsonify({"arduinos_info": data})


# -----------------------------
# ROUTE POUR ENVOYER UNE ACTION MANUELLE
# -----------------------------
@app.route("/set_action/<name>", methods=["POST"])
def set_action(name):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if name not in arduinos:
        return f"Arduino '{name}' inconnu.", 404
    action = request.form.get("action", "").strip()
    # Si aucune action choisie → on ne fait rien
    if not action:
        return redirect("/home")
    # Initialiser la file d’attente si absente
    if name not in arduinos:
        arduinos[name] = {"actions": []}
    if "actions" not in arduinos[name]:
        arduinos[name]["actions"] = []
    # Ajouter l'action dans la file FIFO
    arduinos[name]["actions"].append(action)
    print(f"[ACTION MANUELLE] Ajout pour {name} : {action}")
    return redirect("/home")


# -----------------------------
# PAGE WEB POUR VARIABLES SRV
# -----------------------------
@app.route("/arduino_variables")
def arduino_variables():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    arduino_name = request.args.get("arduino_name")
    if not arduino_name or arduino_name not in arduinos:
        return f"Erreur : Arduino '{arduino_name}' inconnu", 404
    return render_template_string("""
    <html>
    <head>
        <title>Variables - {{arduino_name}}</title>
        <style>
            body { font-family: Arial; background:#f7f7f7; margin:20px; }
            table { border-collapse: collapse; width: 80%; background:white;
                    box-shadow:0 0 10px rgba(0,0,0,0.1); }
            th, td { padding:8px; border:1px solid #ddd; text-align:center; }
            th { background:#0078D7; color:white; }
            tr:nth-child(even){ background:#f2f2f2; }
            .led-on  { width:16px; height:16px; background:#00cc00; border-radius:50%; margin:auto; }
            .led-off { width:16px; height:16px; background:#cc0000; border-radius:50%; margin:auto; }
            button { padding:6px 10px; margin:2px; cursor:pointer; }
        </style>
        <script>
            async function refreshData() {
                try {
                    const res = await fetch('/arduino_vars_status');
                    const data = await res.json();
                    const name = {{ arduino_name|tojson }};
                    const arduino = data[name];
                    if (!arduino) {
                        document.getElementById('vars-body').innerHTML = '<tr><td colspan="4">Aucune donnée</td></tr>';
                        return;
                    }
                    const table = document.getElementById("vars-body");
                    table.innerHTML = "";
                    const applications = arduino.variables_srv || {};
                    for (const appName in applications) {
                        const vars = applications[appName];
                        for (const fullName in vars) {
                            const rawVal = vars[fullName];
                            const v = Number(rawVal) || 0;
                            // shortName = remove "app.type." prefix -> keep everything after the second dot
                            const parts = fullName.split('.');
                            const shortName = (parts.length > 2) ? parts.slice(2).join('.') : fullName;
                            const led = v === 1
                                ? '<div class="led-on" title="ON"></div>'
                                : '<div class="led-off" title="OFF"></div>';
                            const row = document.createElement('tr');
                            // Application cell
                            const tdApp = document.createElement('td');
                            tdApp.textContent = appName;
                            row.appendChild(tdApp);
                            // Variable name (short)
                            const tdName = document.createElement('td');
                            tdName.textContent = shortName;
                            row.appendChild(tdName);
                            // Etat (led)
                            const tdLed = document.createElement('td');
                            tdLed.innerHTML = led;
                            row.appendChild(tdLed);
                            // Commandes (ON/OFF) - use data attribute to carry full variable name
                            const tdCmd = document.createElement('td');
                            const btnOn = document.createElement('button');
                            btnOn.textContent = 'ON';
                            btnOn.dataset.name = fullName;
                            btnOn.onclick = () => setVar(btnOn.dataset.name, 1);
                            const btnOff = document.createElement('button');
                            btnOff.textContent = 'OFF';
                            btnOff.dataset.name = fullName;
                            btnOff.onclick = () => setVar(btnOff.dataset.name, 0);
                            tdCmd.appendChild(btnOn);
                            tdCmd.appendChild(btnOff);
                            row.appendChild(tdCmd);
                            table.appendChild(row);
                        }
                    }
                } catch(err) {
                    console.error("Erreur refreshData:", err);
                }
            }
            async function setVar(fullVarName, value) {
                const arduinoName = {{ arduino_name|tojson }};
                try {
                    await fetch("/update_srv_variable", {
                        method:"POST",
                        headers:{ "Content-Type":"application/json" },
                        body: JSON.stringify({
                            key: "{{SECURITY_KEY}}",
                            arduino: arduinoName,
                            variable: fullVarName,
                            value: value
                        })
                    });
                    // rafraîchir l'affichage rapidement pour retour visuel
                    setTimeout(refreshData, 300);
                } catch(err){
                    console.error("Erreur setVar:", err);
                }
            }
            setInterval(refreshData, 2000);
            window.onload = refreshData;
        </script>
    </head>
    <body>
        <h2>⚙ Variables Serveur : {{arduino_name}}</h2>
        <table>
            <thead>
                <tr>
                    <th>Application</th>
                    <th>Nom Variable</th>
                    <th>État</th>
                    <th>Commande</th>
                </tr>
            </thead>
            <tbody id="vars-body">
                <tr><td colspan="4">Chargement…</td></tr>
            </tbody>
        </table>
        <br>
        <a href="/home">⬅ Retour</a>
    </body>
    </html>
    """, arduino_name=arduino_name, SECURITY_KEY=SECURITY_KEY)


@app.route("/arduino_vars_status")
def arduino_vars_status():
    output = {}
    for name, info in arduinos.items():
        output[name] = {
            "variables_srv": info.get("variables_srv", {})
        }
    return jsonify(output)

import re
def update_app_meteo():
    global APP_MODEL
    from app_meteo import cities, update_city_meteo
    city_number = int(APP_MODEL["meteo"]["i"]["city_number"])
    for i in range(1, city_number + 1):
        # Mise à jour météo de la ville i
        update_city_meteo(cities[i - 1])
        # Injection résultats dans le APP_MODEL
        APP_MODEL["meteo"]["s"][f"city_name_{i}"]  = cities[i - 1]["name"]
        tmp_meteo = cities[i - 1]["meteo"]
        tmp_meteo = re.sub("&deg;", "", tmp_meteo)
        print(f'update_app_meteo: tmp_meteo={tmp_meteo}')
        APP_MODEL["meteo"]["s"][f"city_meteo_{i}"] = tmp_meteo
    # --- Sauvegarde persistante ---
    #os.makedirs("/var/data", exist_ok=True)
    os.makedirs("./", exist_ok=True)
    print(f"Fonction update_app_meteo(): bkp APP_MODEL['meteo']=")
    pprint(APP_MODEL['meteo'])
    with open(PERSIST_FILE, "w", encoding="utf-8") as f:
        json.dump(APP_MODEL, f, ensure_ascii=False, indent=2)


@app.route("/meteo")
def meteo_page():
    import json, os
    global APP_MODEL

    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # Charger depuis disque
    if os.path.exists(PERSIST_FILE):
        with open(PERSIST_FILE, "r", encoding="utf-8") as f:
            APP_MODEL = json.load(f)
    print(f'meteo_page: APP_MODEL=')
    pprint(APP_MODEL)
    print(f'var_city_number=')
    var_city_number=APP_MODEL["meteo"]['i']['city_number']
    pprint(var_city_number)
    city_number = int(var_city_number)
    print(f'city_number={city_number}')

    # Construire liste des villes
    cities = []
    for idx in range(1, city_number + 1):
        name = APP_MODEL["meteo"]["s"].get(f"city_name_{idx}", "")
        meteo = APP_MODEL["meteo"]["s"].get(f"city_meteo_{idx}", "")
        cities.append((idx, name, meteo))

    # Icônes météo
    icons = {
        "SOLEIL": "☀️",
        "NUAGEUX": "☁️",
        "BRUME": "🌫️",
        "PLUIE": "☔",
        "NEIGE": "⛄"
    }
    icons = {
        "SOLEIL": "☀️",
        "NUAGEUX": "☁️",
        "BRUME": "≋",
        "PLUIE": "☔",
        "NEIGE": "⛄"
    }

    # Horaire nuit → lune
    def icon_for(hour, weather):
        if weather == "SOLEIL":
            h = int(hour.replace("h", ""))
            if h >= 17 or h < 7:
                return "🌙"
        return icons.get(weather, "❓")

    # Extraire entêtes horaires (à partir de la 1ère ville)
    hour_labels = []
    if cities and cities[0][2]:
        segments = cities[0][2].split("  ")
        hour_labels = [seg.split(":")[0] for seg in segments]

    # HTML ////////////////////////////////////////////////////////
    html = """
    <html>
        <head>
            <meta charset="UTF-8">
            <title>Météo</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f0f4f8;
                    margin: 20px;
                }
                h2 { color: #003366; }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    background: white;
                }
                th {
                    background-color: #2980b9;
                    color: white;
                    padding: 10px;
                    border: 2px solid #1f618d;
                    font-size: 16px;
                    text-align: center;
                }
                td {
                    border: 2px solid #1f618d;
                    padding: 10px;
                    text-align: center;
                    vertical-align: middle;
                }
                tr:nth-child(even) { background-color: #f2faff; }
                .btn {
                    display: inline-block;
                    padding: 10px 16px;
                    background-color: #2980b9;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                }
                .btn:hover { background-color: #1f618d; }
                .formbox {
                    margin-top: 30px;
                    padding: 20px;
                    background: white;
                    border: 2px solid #1f618d;
                    border-radius: 10px;
                }
                input[type=text] {
                    padding: 8px;
                    width: 300px;
                    font-size: 16px;
                }
            </style>
        </head>
        <body>

        <h2>📡 Application Météo</h2>

        <table>
            <tr>
                <th>#</th>
                <th>Ville</th>
    """

    # Ajouter entêtes horaires
    for h in hour_labels:
        html += f"<th>{h}</th>"
    html += "</tr>"

    # Lignes météo
    for idx, name, meteo in cities:
        entries = [seg.strip() for seg in meteo.split("  ") if seg.strip()]
        html += f"<tr><td>{idx}</td><td>{name}</td>"

        for entry in entries:
            try:
                hour, rest = entry.split(":", 1)
                temp, wtype = rest.split(" ", 1)
                wtype = wtype.strip()
                ic = icon_for(hour, wtype)
            except:
                temp = "?"
                ic = "❓"
            html += f"<td>{temp}<br>{ic}</td>"

        html += "</tr>"

    html += "</table>"

    # Bouton refresh
    html += """
    <form action="/update_meteo" method="get">
        <button type="submit" class="btn">🔄 Rafraîchir la météo</button>
    </form>
    """

    # Ajout d’une ville
    html += """
    <div class="formbox">
        <h3>➕ Ajouter une ville</h3>
        <form action="/add_city" method="post">
            <input type="text" name="city_name" placeholder="Nom de la ville" required>
            <br><br>
            <button class="btn" type="submit">Ajouter</button>
        </form>
    </div>
    """

    # Supprimer dernière ville
    html += """
    <form action="/remove_last_city" method="post">
        <button type="submit" class="btn" style="background:#c0392b">🗑️ Supprimer dernière ville</button>
    </form>
    """

    html += '<a href="/home" class="btn">Retour</a>'

    html += "</body></html>"

    return html

@app.route("/add_city", methods=["POST"])
def add_city():
    global APP_MODEL

    name = request.form.get("city_name", "").strip()

    if not name:
        return redirect("/meteo")

    # Incrémenter l'index
    idx = int(APP_MODEL["meteo"]["i"]["city_number"]) + 1
    APP_MODEL["meteo"]["i"]["city_number"] = f'{idx}'

    # Enregistrer la nouvelle ville
    APP_MODEL["meteo"]["s"][f"city_name_{idx}"] = name
    APP_MODEL["meteo"]["s"][f"city_meteo_{idx}"] = ""
    save_persist()  # si tu as une fonction pour sauvegarder
    return redirect("/update_meteo")   # pour récupérer les données météo

@app.route("/remove_last_city", methods=["POST"])
def remove_last_city():
    global APP_MODEL
    count = int(APP_MODEL["meteo"]["i"]["city_number"])

    if count > 0:
        APP_MODEL["meteo"]["s"].pop(f"city_name_{count}", None)
        APP_MODEL["meteo"]["s"].pop(f"city_meteo_{count}", None)
        count_1= count - 1
        APP_MODEL["meteo"]["i"]["city_number"] = f'{count_1}'
    save_persist()
    return redirect("/meteo")

def save_persist():
    """Écrit APP_MODEL['meteo'] dans le fichier de persistance."""
    global APP_MODEL, PERSIST_FILE
    print(f'Fonction save_persist() : bkp APP_MODEL=')
    pprint(APP_MODEL)
    with open(PERSIST_FILE, "w", encoding="utf-8") as f:
        json.dump(APP_MODEL, f, ensure_ascii=False, indent=2)

def load_persist():
    """Recharge APP_MODEL['meteo'] depuis le fichier si présent."""
    global APP_MODEL, PERSIST_FILE
    if os.path.exists(PERSIST_FILE):
        with open(PERSIST_FILE, "r", encoding="utf-8") as f:
            APP_MODEL = json.load(f)
    else:
        # rien à charger
        pass

# --- utilitaires pour géocodage + météo (simple, synchronisé) ---
def geocode_city(name):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(name)}&count=1&language=fr"
    r = requests.get(url, timeout=6)
    if r.status_code != 200:
        return None
    data = r.json()
    if "results" not in data or not data["results"]:
        return None
    return data["results"][0]["latitude"], data["results"][0]["longitude"]

def decode_weather(code):
    if code == 0: return "SOLEIL"
    if code in (1,2,3): return "NUAGEUX"
    if code in (45,48): return "BRUME"
    if (51 <= code <= 67) or (80 <= code <= 82) or (95 <= code <= 99): return "PLUIE"
    if (71 <= code <= 77) or (85 <= code <= 86): return "NEIGE"
    return "INCONNU"

def get_forecast_for_city(name):
    """
    Renvoie la chaîne formatée attendue pour city_meteo_X,
    exemple: "08h:12° SOLEIL 10h:14° NUAGEUX ..." (12 créneaux).
    """
    # 1) géocodage
    geo = geocode_city(name)
    if not geo:
        return ""  # ou "GEO_ERR"
    lat, lon = geo

    # 2) appel open-meteo (compression=none & format=json)
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,weather_code"
        "&timezone=Europe%2FParis"
        "&compression=none&format=json"
    )
    r = requests.get(url, timeout=8)
    if r.status_code != 200:
        return ""

    data = r.json()
    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    codes = data["hourly"]["weather_code"]

    schedule_hours = [8,10,12,14,16,18,20,22,0,2,4,6]

    now_h = datetime.now().hour
    # trouver premier index dans schedule >= now_h, sinon prendre le premier après min
    start_idx = 0
    for i, h in enumerate(schedule_hours):
        if h >= now_h:
            start_idx = i
            break

    parts = []
    for k in range(12):
        target_h = schedule_hours[(start_idx + k) % 12]
        # trouver un index j dans times avec heure == target_h (prend le premier)
        j = next((i for i,t in enumerate(times) if int(t[11:13]) == target_h), None)
        if j is None:
            continue
        tval = int(round(temps[j]))
        wcode = int(codes[j])
        wtext = decode_weather(wcode)
        parts.append(f"{target_h:02d}h:{tval}&deg; {wtext}")

    return "  ".join(parts)



@app.route("/delete_city", methods=["POST"])
def delete_city():
    global APP_MODEL

    city_number = int(APP_MODEL["meteo"]["i"]["city_number"])

    if city_number > 0:
        # Suppression des champs
        del APP_MODEL["meteo"]["s"][f"city_name_{city_number}"]
        del APP_MODEL["meteo"]["s"][f"city_meteo_{city_number}"]

        # Décrémentation
        city_number_1 = city_number - 1
        APP_MODEL["meteo"]["i"]["city_number"] = f'{city_number}'

        # Sauvegarde
        save_persist()

    return redirect("/meteo")



@app.route("/arduino_get_app_vars_names")
def arduino_get_app_vars_names():
    key = request.args.get("key", "")
    app_name = request.args.get("app", "")
    print("Entree dans la fonction : arduino_get_app_vars_names()")
    if key != SECURITY_KEY:
        return "FORBIDDEN", 403
    print("SECURUTY OK : arduino_get_app_vars_names()")
    if app_name not in APP_MODEL:
        return "", 200   # aucune variable
    print("app meteo OK ")
    vars_dict = APP_MODEL[app_name]["s"] | APP_MODEL[app_name]["i"] | APP_MODEL[app_name]["b"]
    # On renvoie seulement les noms, séparés par un ";"
    response = ";".join(vars_dict.keys()) + ";"
    print("Reponse de la fonction:")
    print(response)
    return response, 200


@app.route("/arduino_get_app_var_value")
def arduino_get_app_var_value():
    key = request.args.get("key", "")
    app_name = request.args.get("app", "")
    var_name = request.args.get("var", "")
    if key != SECURITY_KEY:
        return "FORBIDDEN", 403
    if app_name not in APP_MODEL:
        return "", 200
    all_vars = APP_MODEL[app_name]["s"] | APP_MODEL[app_name]["i"] | APP_MODEL[app_name]["b"]
    value = all_vars.get(var_name, "")
    return str(value), 200



# Lancer le thread au démarrage du serveur
update_app_meteo()
threading.Thread(target=meteo_background_task, daemon=True).start()

#print("APP_MODEL:")
#pprint(APP_MODEL)