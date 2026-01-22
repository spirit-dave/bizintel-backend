from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import os

app = Flask(__name__)

# ---------------- CORS CONFIG ----------------
CORS(
    app,
    resources={r"/api/*": {"origins": [
        "http://localhost:5173",
        "https://bizintel.netlify.app"
    ]}}
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
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
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
        print("SCRAPE ERROR:", repr(e), "URL:", url)
        return jsonify({
            "error": "Scraping failed",
            "details": str(e)
        }), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    
    message = data.get("message", "").strip()
    business = data.get("business_data") or {}

    if not message:
        return jsonify({"message": "Please ask a question."}), 400

    if not business:
        return jsonify({
            "message": "I don’t have any business data yet. Please scrape a website first."
        }), 400

    name = business.get("name", "This company")
    description = business.get("description", "")
    emails = business.get("emails", [])
    phones = business.get("phones", [])

    message_lower = message.lower()

    # --- simple AI-like responses ---
    if "market" in message_lower or "sector" in message_lower:
        response = f"{name} operates in multiple sectors. Based on scraped info, its main markets include manufacturing, services, and consumer products."
    elif "competitor" in message_lower:
        response = f"{name}'s competitors vary by industry. Regional companies and multinationals are typically the main competitors."
    elif "revenue" in message_lower or "money" in message_lower:
        response = f"{name}'s revenue primarily comes from its core operations and local market dominance."
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

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Railway sets this automatically
    app.run(host="0.0.0.0", port=port)
