import os
import time
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup

app = Flask(__name__)

# CORS for Netlify + local
CORS(
    app,
    origins=[
        "http://localhost:5173",
        "https://bizintel.netlify.app"
    ]
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}

# ------------------------
# Utilities
# ------------------------

def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def extract_business_data(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")

    emails = list(set(re.findall(r"[\w\.-]+@[\w\.-]+", text)))
    phones = list(set(re.findall(r"\+?\d[\d\s\-]{7,}\d", text)))

    name = soup.title.string.strip() if soup.title else "Unknown Business"

    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = meta_desc["content"] if meta_desc and meta_desc.get("content") else "No description found"

    return {
        "name": name,
        "description": description,
        "emails": emails,
        "phones": phones
    }


def generate_business_insight(message: str, business: dict) -> str:
    msg = message.lower()
    name = business.get("name", "This business")
    description = business.get("description", "")
    emails = business.get("emails", [])
    phones = business.get("phones", [])

    if "market" in msg or "sector" in msg:
        return (
            f"{name} operates within a competitive commercial environment. "
            "Based on available information, its market focus appears aligned "
            "with its public-facing services and offerings."
        )

    if "competitor" in msg:
        return (
            f"{name}'s competitors are likely businesses offering similar services "
            "within the same geographic or digital market."
        )

    if "revenue" in msg or "money" in msg:
        return (
            f"{name}'s revenue model likely combines direct service sales, "
            "client contracts, and repeat business depending on its sector."
        )

    return (
        f"Here is what I know about {name}:\n\n"
        f"{description}\n\n"
        f"Contacts found: {len(emails)} emails, {len(phones)} phone numbers.\n\n"
        "You can ask about markets, competitors, or revenue models."
    )

# ------------------------
# Routes
# ------------------------

@app.route("/api/health")
def health():
    return {"status": "ok"}


@app.route("/api/scrape", methods=["POST"])
def scrape():
    data = request.json or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    url = normalize_url(url)
    start = time.time()

    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()

        business_data = extract_business_data(res.text)
        business_data["scrape_time"] = round(time.time() - start, 2)

        return jsonify(business_data)

    except Exception as e:
        return jsonify({
            "error": "Scraping failed",
            "details": str(e)
        }), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = data.get("message", "").strip()
    business = data.get("business_data")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    if not business:
        return jsonify({"error": "Business data is required"}), 400

    response = generate_business_insight(message, business)

    return jsonify({
        "role": "assistant",
        "message": response
    })


# ------------------------
# Railway entrypoint
# ------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
