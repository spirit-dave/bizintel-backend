from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import google.generativeai as genai

# -------------------------------------------------
# GEMINI CONFIG
# -------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash"

# -------------------------------------------------
# FLASK APP
# -------------------------------------------------
app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:5173",
                "https://bizintel.netlify.app"
            ]
        }
    }
)

# -------------------------------------------------
# SIMPLE IN-MEMORY CACHE
# cache[business_name][question] = response
# -------------------------------------------------
cache = {}

# -------------------------------------------------
# UTIL
# -------------------------------------------------
def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


# -------------------------------------------------
# ROUTES
# -------------------------------------------------
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

        cache.setdefault(business_data["name"], {})

        return jsonify(business_data)

    except Exception as e:
        print("SCRAPE ERROR:", repr(e))
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

    # -------- CACHE HIT --------
    if message in cache[name]:
        return jsonify({
            "role": "assistant",
            "message": cache[name][message],
            "cached": True
        })

    # -------------------------------------------------
    # PROMPT (BUSINESS-FOCUSED, NO HALLUCINATIONS)
    # -------------------------------------------------
    prompt = f"""
You are a senior business intelligence consultant.

Business name:
{name}

Public description:
{description}

Contact signals:
Emails: {emails}
Phones: {phones}

User question:
{message}

Rules:
- Base insights ONLY on available information
- If data is missing, explain logically instead of guessing
- Provide practical, real-world business insight
- No hype, no fluff, no hallucinations
"""

    try:
        model = genai.GenerativeModel(MODEL_NAME)

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 512,
            }
        )

        ai_text = response.text.strip()

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


# -------------------------------------------------
# ENTRY
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
