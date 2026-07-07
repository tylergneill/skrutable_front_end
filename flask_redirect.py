from flask import Flask, render_template

PROD_URL = "https://skrutable.info"

app = Flask(__name__)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return render_template("redirect.html", prod_url=PROD_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011)
