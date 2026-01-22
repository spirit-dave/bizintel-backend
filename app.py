from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)

# ✅ CORS — allow Netlify frontend
CORS(
    app,
    resources={r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "https://bizintel.netlify.app"
        ]
    }}
)

# ---------------- UTIL ----------------

def normalize_url(url):
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url

# ---------------- ROUTES ----------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/api/scrape", methods=["POST"])
def scrape():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "URL is required"}), 400

    url = normalize_url(data["url"])
    start = time.time()

    try:
        res = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            }
        )

        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(" ")

        emails = list(set(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text)))
        phones = list(set(re.findall(r"\+?\d[\d\s\-]{7,}\d", text)))

        business_data = {
            "name": soup.title.string.strip() if soup.title else "Unknown Business",
            "description": (
                soup.find("meta", attrs={"name": "description"}) or {}
            ).get("content", "No description found"),
            "emails": emails,
            "phones": phones,
            "metadata": f"Scraped in {round(time.time() - start, 2)}s"
        }

        return jsonify(business_data)

    except Exception as e:
        print("SCRAPE ERROR:", repr(e))
        return jsonify({
            "error": "Scraping failed",
            "details": str(e)
        }), 500

# ---------------- ENTRY ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
