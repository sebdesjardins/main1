import requests
from datetime import datetime

# ---- Structure initiale : seulement noms de villes ----
cities = [
    {"name": "Noisy-le-Grand", "meteo": ""},
    {"name": "Paris", "meteo": ""},
    {"name": "Montreuil", "meteo": ""},
    {"name": "Mortagne-sur-Sèvre", "meteo": ""},
    {"name": "Guiche", "meteo": ""},
    {"name": "Came", "meteo": ""}
]

# ---- Créneaux horaires ----
schedule_hours = [ 10, 12, 14, 16, 18, 20, 22, 0, 2, 4, 6, 8,]

# ---- Décodage des weather codes ----
def decode_weather(code):
    if code == 0:
        return "SOLEIL"
    elif code in [1, 2, 3]:
        return "NUAGEUX"
    elif code in [45, 48]:
        return "BRUME"
    elif (51 <= code <= 67) or (80 <= code <= 82) or (95 <= code <= 99):
        return "PLUIE"
    elif (71 <= code <= 77) or (85 <= code <= 86):
        return "NEIGE"
    else:
        return "?"

# ---- Recherche latitude/longitude à partir du nom ----
def geocode_city(name):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1&language=fr&format=json"

    r = requests.get(url)
    if r.status_code != 200:
        return None, None

    data = r.json()

    if "results" not in data or len(data["results"]) == 0:
        return None, None

    lat = data["results"][0]["latitude"]
    lon = data["results"][0]["longitude"]

    return lat, lon


# ---- Mise à jour météo d’une ville ----
def update_city_meteo(city):
    # Étape 1 : géocodage
    lat, lon = geocode_city(city["name"])
    if lat is None:
        city["meteo"] = "Géocodage impossible"
        return

    # Étape 2 : appel météo
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,weather_code"
        "&timezone=Europe/Paris"
        "&compression=none&format=json"
    )
    print(f'{city}, {lat}, {lon}')

    r = requests.get(url)
    if r.status_code != 200:
        city["meteo"] = "Erreur API météo"
        return

    data = r.json()
    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    codes = data["hourly"]["weather_code"]

    # Heure locale actuelle
    now_hour = datetime.now().hour

    # Détermine le premier créneau >= heure actuelle
    start_idx = 0
    for i, h in enumerate(schedule_hours):
        if h >= now_hour:
            start_idx = i
            break

    # Construction de la ligne forecast
    forecast = ""
    for i in range(12):
        h = schedule_hours[(start_idx + i) % 12]

        # Chercher cet horaire dans la liste de l’API
        idx = next((j for j, t in enumerate(times) if int(t[11:13]) == h), None)

        if idx is not None:
            forecast += (
                f"{h:02d}h:{int(temps[idx])} {decode_weather(codes[idx])}  "
            )
    print(f'update_city_meteo: forecast={forecast}')
    city["meteo"] = forecast.strip()

def display_meteo():
    # ---- Mise à jour de toutes les villes ----
    for city in cities:
        update_city_meteo(city)

    # ---- Affichage résultat ----
    print("=== RÉSULTAT ===")
    for city in cities:
        print(city["name"])
        print(city["meteo"])
        print("----------------")

display_meteo()