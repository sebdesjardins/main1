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
        "message": f"Bonjour {name}, connexion HTTPS réussie.",
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

# -----------------------------
# PAGE PRINCIPALE /HOME
# -----------------------------
@app.route("/home")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    html = """
    <html>
    <head>
        <title>Arduino Monitor (AJAX + Anim)</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f7f7f7; margin: 20px; }
            table { border-collapse: collapse; width: 80%; background: white; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            th, td { padding: 10px; text-align: center; border: 1px solid #ddd; }
            th { background-color: #0078D7; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .ok { color: green; font-weight: bold; }
            .off { color: red; font-weight: bold; }
            .fade-green { animation: flashGreen 0.8s ease; }
            .fade-red { animation: flashRed 0.8s ease; }
            @keyframes flashGreen {
                from { background-color: #c6f6c6; }
                to { background-color: white; }
            }
            @keyframes flashRed {
                from { background-color: #f8c6c6; }
                to { background-color: white; }
            }
            .logout { margin-top: 15px; }
        </style>
        <script>
            let previousStatus = {};

            async function refreshData() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    const tableBody = document.getElementById('arduino-table-body');
                    tableBody.innerHTML = '';

                    for (const [name, info] of Object.entries(data.arduinos)) {
                        const wasConnected = previousStatus[name];
                        const row = document.createElement('tr');

                        // Ajoute effet visuel selon changement d’état
                        if (wasConnected !== undefined && wasConnected !== info.connected) {
                            if (info.connected) row.classList.add('fade-green');
                            else row.classList.add('fade-red');
                        }

                        row.innerHTML = `
                            <td>${name}</td>
                            <td>${info.last_seen}</td>
                            <td class="${info.connected ? 'ok' : 'off'}">
                                ${info.connected ? '✅ Connecté' : '❌ Hors ligne'}
                            </td>
                            <td>${info.action || '(aucune)'}</td>
                            <td>
                                <form method="POST" action="/set_action/${name}">
                                    <select name="action">
                                        <option value="">Aucune</option>
                                        <option value="conexion_https_ok()">conexion_https_ok()</option>
                                    </select>
                                    <input type="submit" value="Envoyer">
                                </form>
                            </td>`;
                        tableBody.appendChild(row);

                        previousStatus[name] = info.connected;
                    }

                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                } catch (err) {
                    console.error("Erreur AJAX:", err);
                }
            }

            setInterval(refreshData, 3000);
            window.onload = refreshData;
        </script>
    </head>
    <body>
        <h2>🛰️ Tableau de bord des Arduinos</h2>
        <p>Dernière actualisation : <span id="last-update">--:--:--</span></p>

        <table>
            <thead>
                <tr>
                    <th>Nom</th>
                    <th>Dernière connexion</th>
                    <th>Statut</th>
                    <th>Action actuelle</th>
                    <th>Envoyer Action</th>
                </tr>
            </thead>
            <tbody id="arduino-table-body"></tbody>
        </table>

        <div class="logout">
            <form action="/logout" method="POST">
                <input type="submit" value="🚪 Se déconnecter">
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

# -----------------------------
# ROUTE AJAX /STATUS
# -----------------------------
@app.route("/status")
def status():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 403

    now = datetime.utcnow()
    for name, info in arduinos.items():
        info["connected"] = (now - info["last_seen"]).total_seconds() <= 10

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
# DÉCONNEXION
# -----------------------------
@app.route("/logout", methods=["POST"])
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

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
