from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import openai

# ---------------- OpenAI API ----------------
openai.api_key = os.environ.get("OPENAI_API_KEY")  # Set on Railway

# ---------------- Flask App ----------------
app = Flask(__name__)

# ---------------- CORS ----------------
CORS(
    app,
    resources={r"/api/*": {"origins": [
        "http://localhost:5173",
        "https://bizintel.netlify.app"
    ]}}
)

# ---------------- Cache ----------------
# Simple in-memory cache: {business_name: {question: response}}
cache = {}

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

        # Initialize cache for this business if not exists
        if business_data["name"] not in cache:
            cache[business_data["name"]] = {}

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
        return jsonify({"message": "Please scrape a website first."}), 400

    name = business.get("name", "Unknown Business")

    # Initialize cache for this business if not exists
    if name not in cache:
        cache[name] = {}

    # Check if this question was already asked
    if message in cache[name]:
        return jsonify({
            "role": "assistant",
            "message": cache[name][message],
            "cached": True
        })

    # Prepare context for GPT
    context = f"""
    You are a helpful business analyst. Use the following scraped information to answer questions:

    Company Name: {name}
    Description: {business.get('description', '')}
    Emails: {business.get('emails', [])}
    Phones: {business.get('phones', [])}
    """

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
        )

        ai_response = completion.choices[0].message["content"]

        # Save in cache
        cache[name][message] = ai_response

        return jsonify({
            "role": "assistant",
            "message": ai_response,
            "cached": False
        })

    except Exception as e:
        print("AI ERROR:", repr(e))
        return jsonify({"error": "AI generation failed", "details": str(e)}), 500

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
