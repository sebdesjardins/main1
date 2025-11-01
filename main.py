
from flask import Flask, request, Response, jsonify, abort, render_template_string, redirect, url_for

from markupsafe import escape
from datetime import datetime
import os
import json

app = Flask(__name__)
data ={}

# Fonction utilitaire : aller chercher une valeur par chemin
def get_value_by_path(data, path):
    """
    Récupère une valeur dans un dict JSON en utilisant un chemin du type
    "application_01.application_name" ou "ARDUINO_EB20.pins.0.name".
    """
    keys = path.split(".")
    current = data
    try:
        for key in keys:
            # Si c'est un entier, on considère que c'est un index de liste
            if key.isdigit():
                idx = int(key)
                current = current[idx]
            else:
                # Si current est une liste de 1 élément, prendre le premier
                if isinstance(current, list) and len(current) == 1:
                    current = current[0]
                current = current[key]
        return current
    except (KeyError, IndexError, TypeError) as e:
        return f"ERROR: {str(e)}"

# Fonction utilitaire : mettre à jour une valeur par chemin
def set_value_by_path(data, path, value):
    keys = path.split(".")
    d = data
    for i, key in enumerate(keys):
        if i == len(keys) - 1:
            d[key] = value
        else:
            # si key est un entier → on accède à une liste
            if key.isdigit():
                key = int(key)
            d = d[key]


def save_data():
    data['date'] = datetime.now().strftime("%d/%m/%Y")
    data['heure']=datetime.now().strftime("%H:%M:%S")
    with open(database_json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

SECRET_KEY = "Private_Key_Data_Srv.20250912.Json.Application"
database_json_file="./arduino_database.json"

if os.path.exists(database_json_file):
    with open(database_json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    # Si la database n'existe pas on l'initialise
    data = {
        'service' : "OK",
        'date' : '12/09/2025',
        'heure' : '10:12:35',
        'applications_list' : 'hello,lecture_humidite,arrosage,distance',
        'application_00': [ { 'application_name': 'hello', 'index' : 0, 'dst_arduino_name_list' :'ARDUINO_EB20,ARDUINO_EB30', 'ARDUINO_EB20': 'off', 'ARDUINO_EB30': 'off' }],
        'application_01': [ { 'application_name': 'lecture_humidite', 'index' : 1, 'arduino_name_list' : 'ARDUINO_EB20,ARDUINO_EB30', 'pot_01': '100', 'pot_02': '200', 'pot_03': '300', }],
        'application_02': [ { 'application_name': 'arrosage', 'index' : 2, 'arduino_name_list' : 'ARDUINO_EB20,ARDUINO_EB30', 'pot_01': 'off', 'pot_02': 'off', 'pot_03': 'off', }],
        'application_03': [ { 'application_name': 'distance', 'index' : 3, 'arduino_name_list' : 'ARDUINO_EB20,ARDUINO_EB30', 'capteur_1': '250', 'capteur_2': '250', 'capteur_3': '50','capteur_4': '50' }]

    }
    save_data()

@app.route("/arduino_get_pin", methods=["GET"])
def get_pin_config():
    arduino_name = request.args.get("arduino")  # ex: "ARDUINO_EB20"
    pin_name = request.args.get("pin")          # ex: "D1"

    try:
        if arduino_name not in data:
            return f"ERROR: Arduino '{arduino_name}' introuvable", 404

        pins = data[arduino_name][0]["pins"]
        for p in pins:
            if p["name"] == pin_name:
                return f"{p['pin']},{p['name']},{p['input_type']},{p['digital_out']},{p['analogique_out']},{p['used_pin']},{p['in_out']},{p['digital_value']},{p['analogique_value']}"

        return f"ERROR: Pin {pin_name} introuvable", 404

    except Exception as e:
        return f"ERROR: {str(e)}", 400




@app.route("/arduino_set_pin", methods=["POST"])
def set_pin_config():
    try:
        body = request.get_json(force=True)
        arduino_name = body.get("arduino")
        config_str = body.get("config")

        if not arduino_name or not config_str:
            return "Erreur: paramètres manquants", 400

        fields = config_str.split(";")
        if len(fields) != 9:
            return "Erreur: format invalide (9 champs attendus)", 400

        pin_index = int(fields[0])

        if arduino_name not in data:
            return f"Erreur: {arduino_name} non trouvé", 404

        arduino_struct = data[arduino_name][0]

        if pin_index < 0 or pin_index >= len(arduino_struct["pins"]):
            return "Erreur: index de pin invalide", 400

        # Mettre à jour la config
        arduino_struct["pins"][pin_index] = {
            "pin": fields[0],
            "name": fields[1],
            "input_type": fields[2],
            "digital_out": fields[3],
            "analogique_out": fields[4],
            "used_pin": fields[5],
            "in_out": fields[6],
            "digital_value": fields[7],
            "analogique_value": fields[8]
        }

        save_data()
        return "OK", 200

    except Exception as e:
        return f"Erreur: {str(e)}", 500


# ---------------------
# Route GET → lecture
# ---------------------
@app.route("/arduino_data_srv", methods=["GET"])
def get_arduino_var():
    var_path = request.args.get("var")  # ex: ?var=ARDUINO_EB20.0.pins.0.name
    try:
        # Si la variable demandée est "date" ou "heure"
        if var_path == "date":
            data["date"] = datetime.now().strftime("%d/%m/%Y")
            save_data()
            value = data["date"]

        elif var_path == "heure":
            data["heure"] = datetime.now().strftime("%H:%M:%S")
            save_data()
            value = data["heure"]
        else:
            # Sinon on prend la valeur directement depuis la structure JSON
            value = get_value_by_path(data, var_path)
        # Retourne la valeur sous forme de texte ou JSON
        if isinstance(value, (dict, list)):
            return jsonify(value)
        else:
            return str(value)
    except Exception as e:
        return f"ERROR: {str(e)}", 404

# ---------------------
# Route POST → écriture
# ---------------------
@app.route("/arduino_data_srv", methods=["POST"])
def set_arduino_var():
    try:
        print("Headers:", dict(request.headers))
        print("Raw data:", request.data)
        body = request.get_json(force=True)
        print("JSON reçu:", body)

        var_path = body.get("var")
        value = body.get("value")

        set_value_by_path(data, var_path, value)
        save_data()
        return jsonify("OK")

    except Exception as e:
        return f"ERROR: {str(e)}", 400

@app.route("/data_srv", methods=["GET"])
def get_variables():
    #api_key = request.headers.get("x-api-key")
    #if api_key != SECRET_KEY:
    #    abort(401, description="Clé d'authentification invalide")

    save_data()
    var_name = request.args.get("var")
    if not var_name:
        # ✅ Aucun paramètre → on retourne toutes les variables
        return jsonify(data)
    if var_name not in data:
        return jsonify({"ERROR": f"La variable '{var_name}' n'existe pas"}), 404
    return jsonify({var_name: data[var_name]})


@app.route("/list_vars", methods=["GET"])
def list_variables():
    api_key = request.headers.get("x-api-key")
    if api_key != SECRET_KEY:
        abort(401, description="Clé d'authentification invalide")

    # Retourne uniquement la liste des clés de "data"
    return jsonify({"variables": list(data.keys())})

@app.route("/data_srv", methods=["POST"])
def write_variables():
    api_key = request.headers.get("x-api-key")
    if api_key != SECRET_KEY:
        abort(401, description="Clé d'authentification invalide")

    # JSON attendu : {"var": "nom_variable", "value": valeur}
    content = request.get_json()
    if not content or "var" not in content or "value" not in content:
        return jsonify({"ERROR": "JSON invalide. Doit contenir 'var' et 'value'"}), 400

    var_name = content["var"]
    value = content["value"]

    if var_name == 'applications_list':
        return jsonify({"ERROR": "Modification interdite pour la variable : applications_list"}), 400

    # Mise à jour de la variable
    data[var_name] = value
    save_data()
    return jsonify({"success": True, var_name: data[var_name]})

@app.route("/arduino_create", methods=["GET"])
def arduino_create():
    arduino_name = request.args.get("var")  # Nom de l’arduino, ex: ARDUINO_XXXX
    if not arduino_name:
        return "Erreur: nom de l'Arduino manquant", 400
    # Vérifier si l’Arduino existe déjà
    if arduino_name in data:
        return f"Erreur: {arduino_name} existe déjà", 400

    # Création de la structure vide
    new_arduino = [
        {
            "applications": "",
            "variables": [
                {
                    "arduino_name": arduino_name,
                    "arduino_type": "",
                    "arduino_adresse_ip": "",
                    "arduino_mc_address": "",
                    "arduino_data_srv_ip": ""
                }
            ],
            "pins": []
        }
    ]
    # Génération des 20 pins
    pin_definitions = [
        ("0", "D0", "DIGITALE"),
        ("1", "D1", "DIGITALE"),
        ("2", "D2", "DIGITALE"),
        ("3", "D3", "DIGITALE"),
        ("4", "D4", "DIGITALE"),
        ("5", "D5", "DIGITALE"),
        ("6", "D6", "DIGITALE"),
        ("7", "D7", "DIGITALE"),
        ("8", "D8", "DIGITALE"),
        ("9", "D9", "DIGITALE"),
        ("10", "D10", "DIGITALE"),
        ("11", "D11", "DIGITALE"),
        ("12", "D12", "DIGITALE"),
        ("13", "D13", "DIGITALE"),
        ("14", "A0", "ANALOGIQUE"),
        ("15", "A1", "ANALOGIQUE"),
        ("16", "A2", "ANALOGIQUE"),
        ("17", "A3", "ANALOGIQUE"),
        ("18", "A4", "ANALOGIQUE"),
        ("19", "A5", "ANALOGIQUE"),
    ]
    for pin, name, input_type in pin_definitions:
        new_arduino[0]["pins"].append({
            "pin": pin,
            "name": name,
            "input_type": input_type,
            "digital_out": "true",
            "analogique_out": "true" if name in ["D3", "D5", "D6", "D9", "D10", "D11"] else "false",
            "used_pin": "true" if pin not in ["18", "19"] else "false",
            "in_out": "OUTPUT",
            "digital_value": "LOW",
            "analogique_value": "0"
        })
    # Ajouter au dictionnaire global
    data[arduino_name] = new_arduino
    save_data()
    return f"{arduino_name} créé avec succès", 200



@app.route('/arduinos_config')
def arduinos_config():
    # Récupère uniquement les clés correspondant aux Arduinos
    arduino_keys = [k for k in data if k.startswith('ARDUINO_')]

    # Récupère le nom choisi via le paramètre GET
    arduino_name = request.args.get('arduino_name')

    # Si aucun Arduino choisi ou clé invalide, prendre le premier disponible
    if not arduino_name or arduino_name not in arduino_keys:
        arduino_name = arduino_keys[0]

    # Récupère la configuration correspondante
    arduino = data[arduino_name][0]

    html = """
    <html>
    <head>
        <title>Configuration Arduino</title>
    </head>
    <body>
        <h2>Choisir un Arduino</h2>
        <form method="get" action="/arduinos_config">
            <label for="arduino_select">Arduino :</label>
            <select id="arduino_select" name="arduino_name">
                {% for name in arduino_keys %}
                    <option value="{{ name }}" {% if name == arduino_name %}selected{% endif %}>
                        {{ name }}
                    </option>
                {% endfor %}
            </select>
            <button type="submit">Afficher</button>
        </form>
        <hr>

        <h2>Variables de l'Arduino {{ arduino_name }}</h2>
        <table border="1" cellpadding="5">
            <tr style="background-color: #d3d3d3; text-align:center;">
                <th>Nom</th>
                <th>Valeur</th>
            </tr>
            {% for var in arduino['variables'] %}
                {% for key, value in var.items() %}
                <tr>
                    <td style="background-color: #f0f0f0; text-align:center;">{{ key }}</td>
                    <td style="text-align:center;">{{ value }}</td>
                </tr>
                {% endfor %}
            {% endfor %}
        </table>

        <h3>Pins</h3>
        <table border="1" cellpadding="5">
            <tr style="background-color: #f0f0f0; text-align:center;">
                <th>Pin</th><th>Name</th><th>Type</th><th>Digital Out</th><th>Analog Out</th>
                <th>Used</th><th>In/Out</th><th>Digital Value</th><th>Analog Value</th>
            </tr>
            {% for pin in arduino['pins'] %}
            <tr>
                <td style="background-color: #f0f0f0; text-align:center;">{{ pin['pin'] }}</td>
                <td style="background-color: #f0f0f0; text-align:center;">{{ pin['name'] }}</td>
                <td style="background-color: #f0f0f0; text-align:center;">{{ pin['input_type'] }}</td>
                <td style="background-color: #f0f0f0; text-align:center;">
                    {% if pin['digital_out'] == 'true' %}DIGITALE{% endif %}
                </td>
                <td style="background-color: #f0f0f0; text-align:center;">
                    {% if pin['analogique_out'] == 'true' %}ANALOGIQUE{% endif %}
                </td>
                <td style="text-align:center;">
                    {% if pin['used_pin'] == 'true' %}Active{% else %}Reservee{% endif %}
                </td>
                {% if pin['used_pin'] == 'true' %}
                    <td style="text-align:center;">{{ pin['in_out'] }}</td>
                    <td style="text-align:center;">{{ pin['digital_value'] }}</td>
                    <td style="text-align:center;">{{ pin['analogique_value'] }}</td>
                {% else %}
                    <td style="background-color: #d3d3d3; text-align:center;"></td>
                    <td style="background-color: #d3d3d3; text-align:center;"></td>
                    <td style="background-color: #d3d3d3; text-align:center;"></td>
                {% endif %}
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """

    return render_template_string(html, arduino_keys=arduino_keys, arduino_name=arduino_name, arduino=arduino)


@app.route('/variables_view')
def variables_view():
    # On récupère toutes les clés de data qui correspondent aux applications
    app_keys = [k for k in data.keys() if k.startswith('application_')]

    html = """
    <html>
    <head>
        <title>Variables Applications</title>
    </head>
    <body>
        <h2>Variables des Applications</h2>
        {% for app_key in app_keys %}
            <h3>{{ app_key }}</h3>
            <table border="1" cellpadding="5">
                <tr style="background-color: #f0f0f0;">
                    <th style="text-align:center">Index</th>
                    <th style="text-align:center">Variable</th>
                    <th style="text-align:center">Valeur</th>
                    <th style="text-align:center">Modifier</th>
                </tr>
                {% for key, value in data[app_key][0].items() %}
                <tr>
                    <th style="text-align:center; background-color: #f0f0f0;">{{ loop.index0 }}</th>
                    <th style="text-align:left; background-color: #f0f0f0;">{{ key }}</th>
                    <td style="text-align:left; background-color: #f0f0f0;">{{ value }}</td>
                    <td style="text-align:center; background-color: #000000;">
                        <form action="/set_variable_app" method="GET">
                            <input type="hidden" name="app_key" value="{{ app_key }}">
                            <input type="hidden" name="variable" value="{{ key }}">
                            <input type="text" name="value" value="{{ value }}" style="width:120px; text-align:center;">
                            <input type="submit" value="Modifier">
                        </form>
                    </td>
                </tr>
                {% endfor %}

                <!-- Ligne spéciale pour ajout d'une nouvelle variable -->
                <tr>
                    <th style="text-align:center; background-color: #f0f0f0;">{{ data[app_key][0]|length }}</th>
                    <td style="text-align:left; background-color: #f0f0f0;">
                        <form action="/set_variable_app" method="GET" style="margin:0;">
                            <input type="hidden" name="app_key" value="{{ app_key }}">
                            <input type="hidden" name="new_var" value="true">
                            <input type="text" name="variable" value="Nouvelle variable" style="width:120px; text-align:left;">
                    </td>
                    <td style="text-align:left; background-color: #f0f0f0;">
                            <input type="text" name="value" value="Nouvelle valeur" style="width:120px; text-align:left;">
                    </td>
                    <td style="text-align:center; background-color: #000000;">
                            <input type="submit" value="Ajouter">
                        </form>
                    </td>
                </tr>
            </table>
            <br>
        {% endfor %}
    </body>
    </html>
    """
    return render_template_string(html, data=data, app_keys=app_keys)


@app.route('/set_variable_app')
def set_variable_app():
    app_key = request.args.get("app_key")
    variable = request.args.get("variable")
    value = request.args.get("value")
    new_var = request.args.get("new_var")

    if app_key in data:
        if new_var:
            # Ajouter une nouvelle variable
            data[app_key][0][variable] = value
        else:
            # Modifier une variable existante
            if variable in data[app_key][0]:
                data[app_key][0][variable] = value
        save_data()

    # On revient sur la vue des variables
    return redirect(url_for('variables_view'))






@app.route("/arduino_set_variables", methods=["POST"])
def arduino_set_variables():
    try:
        body = request.get_json(force=True)
        arduino_name = body.get("arduino")
        config_str = body.get("config")

        if not arduino_name or not config_str:
            return "Erreur: paramètres manquants", 400

        fields = [f for f in config_str.split(";") if f.strip()]

        if len(fields) % 2 != 0:
            return "Erreur: config mal formée", 400

        # Mise à jour des variables
        for i in range(0, len(fields), 2):
            key = fields[i]
            value = fields[i + 1]
            data[arduino_name][0]["variables"][0][key] = value

        save_data()
        return "OK", 200

    except Exception as e:
        return f"Erreur: {str(e)}", 500




def build_ordered_string(entry: dict) -> str:
    parts = []
    # 1) index puis sa valeur (si présent)
    if 'index' in entry:
        parts.append('index')
        parts.append(str(entry['index']))
    # 2) application_name puis sa valeur (si présent)
    if 'application_name' in entry:
        parts.append('application_name')
        parts.append(str(entry['application_name']))
    # 3) les autres champs dans l'ordre d'apparition du dict
    for k, v in entry.items():
        if k in ('index', 'application_name'):
            continue
        parts.append(str(k))
        parts.append(str(v))
    # joindre et ajouter ; final
    return ';'.join(parts) + ';'

@app.route('/application_variables_get')
def application_variables_get():
    appname = request.args.get('application_name')
    if not appname:
        html = "<h3>Erreur: paramètre 'application_name' manquant.</h3>"
        return Response(html, status=400, mimetype='text/html',
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                                 "Pragma": "no-cache", "Expires": "0"})

    # parcourir data pour trouver l'entrée qui a application_name == appname
    for key, lst in data.items():
        if not isinstance(lst, list):
            continue
        for entry in lst:
            if not isinstance(entry, dict):
                continue
            if entry.get('application_name') == appname:
                result_str = build_ordered_string(entry)
                safe = escape(result_str)
                html = f"<html><body><pre>{safe}</pre></body></html>"
                return Response(result_str, status=200, mimetype='text/plain',
                                headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                                         "Pragma": "no-cache", "Expires": "0"})

    # si non trouvé
    html = f"<h3>Application '{escape(appname)}' non trouvée.</h3>"
    return Response(html, status=404, mimetype='text/html',
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)
