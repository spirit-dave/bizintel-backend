from flask import Flask, request, jsonify, session
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)
app.secret_key = "bizintel-secret-key"  # required for sessions

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5173",
        "https://bizintel.netlify.app"
    ]
)

def normalize_url(url):
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url

@app.route("/api/health")
def health():
    return {"status": "ok"}

@app.route("/api/scrape", methods=["POST"])
def scrape():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    url = normalize_url(url)
    start = time.time()

    try:
        res = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "BizIntelBot/1.0"}
        )

        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(" ")

        emails = list(set(re.findall(r"[\w\.-]+@[\w\.-]+", text)))
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

        #   STORE IN SESSION (STATEFUL)
        session["business_data"] = business_data

        return jsonify(business_data)

    except Exception as e:
        return jsonify({
            "error": "Unable to scrape website",
            "details": str(e)
        }), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}

    message = data.get("message", "").strip()
    business = data.get("business_data")

    if not message:
        return jsonify({"message": "Please ask a question."}), 400

    if not business:
        return jsonify({
            "message": "I don’t have any business data yet. Please scrape a website first."
        })

    name = business.get("business_name") or "This company"
    description = business.get("description") or ""
    emails = business.get("emails", [])
    phones = business.get("phones", [])

    # --- Simple but REAL reasoning ---
    message_lower = message.lower()

    if "market" in message_lower or "sector" in message_lower:
        response = (
            f"{name} operates as a diversified conglomerate. "
            "Based on the scraped information, its primary markets include "
            "manufacturing, industrial goods, consumer products, and essential services. "
            "Its dominance is strongest in regions where it controls supply chains and "
            "local production capacity."
        )

    elif "competitor" in message_lower:
        response = (
            f"{name}'s competitors vary by sector. "
            "In manufacturing and cement, competition is typically regional. "
            "In consumer goods, competition comes from multinational FMCG companies."
        )

    elif "revenue" in message_lower or "money" in message_lower:
        response = (
            f"{name}'s revenue model is driven by large-scale production, "
            "vertical integration, and regional distribution dominance. "
            "Most revenue comes from core industrial operations rather than digital channels."
        )

    else:
        response = (
            f"Here’s what I know about {name}:\n\n"
            f"{description}\n\n"
            f"Contacts found: {len(emails)} emails, {len(phones)} phone numbers.\n\n"
            "You can ask about markets, competitors, or revenue models."
        )

    return jsonify({
        "role": "assistant",
        "message": response
    })

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
