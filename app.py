from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import os
from google.genai import Client

# ---------------- GEMINI SETUP ----------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set in environment variables")

client = Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3-flash-1"  # Latest Gemini 3 Flash model

# ---------------- FLASK APP ----------------
app = Flask(__name__)

# ---------------- CORS ----------------
CORS(
    app,
    resources={r"/api/*": {"origins": [
        "http://localhost:5173",
        "https://bizintel.netlify.app"
    ]}}
)

# ---------------- CACHE ----------------
# Structure: cache[business_name][question] = response
cache = {}

# ---------------- UTILS ----------------
def normalize_url(url: str) -> str:
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

        # Initialize cache for this business
        cache.setdefault(business_data["name"], {})

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
    business = data.get("business_data")

    if not message:
        return jsonify({"message": "Please ask a question."}), 400
    if not business:
        return jsonify({"message": "Please scrape a website first."}), 400

    name = business.get("name", "Unknown Business")
    description = business.get("description", "")
    emails = ", ".join(business.get("emails", [])) or "None found"
    phones = ", ".join(business.get("phones", [])) or "None found"

    cache.setdefault(name, {})

    # Return cached response if exists
    if message in cache[name]:
        return jsonify({
            "role": "assistant",
            "message": cache[name][message],
            "cached": True
        })

    # -------- SMART PROMPT --------
    prompt = f"""
You are a senior business intelligence analyst.

Business Name:
{name}

Description:
{description}

Emails:
{emails}

Phone Numbers:
{phones}

User Question:
{message}

Instructions:
- Think step by step
- Be clear and practical
- Do NOT hallucinate facts
- If information is missing, explain logically
- Give insights a real consultant would give
"""

    try:
        response = client.generate_text(
            model=MODEL_NAME,
            prompt=prompt,
            temperature=0.7,
            max_output_tokens=500
        )
        ai_text = response.text.strip()

        # Save to cache
        cache[name][message] = ai_text

        return jsonify({
            "role": "assistant",
            "message": ai_text,
            "cached": False
        })

    except Exception as e:
        print("AI ERROR:", repr(e))
        return jsonify({
            "error": "AI generation failed",
            "details": str(e)
        }), 500


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
