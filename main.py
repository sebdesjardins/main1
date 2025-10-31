from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Hello from Flask on Render!</h1>"

# Flask utilise 'app' comme instance, Render le lancera via Gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)