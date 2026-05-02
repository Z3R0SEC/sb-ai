import os
import sqlite3, requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DB = "chat.db"       
key = os.getenv("key")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
HEADERS = {"Content-Type": "application/json"}

brain = "Your name is SB, minimalist AI assistant. Be brief, no greetings unless user greets first, no follow-up questions."


@app.errorhandler(404)
def not_found(e): return jsonify({"status":"error","code":404,"message":"Route not found"}),404                                 
@app.errorhandler(405)
def method_not_allowed(e): return jsonify({"status":"error","code":405,"message":"Method not allowed"}),405

@app.errorhandler(400)
def bad_request(e): return jsonify({"status":"error","code":400,"message":"Bad request"}),400

@app.errorhandler(500)
def internal_error(e): return jsonify({"status":"error","code":500,"message":"Server error"}),500

@app.errorhandler(Exception)
def all_exception(e): return jsonify({"status":"error","code":500,"message":str(e)}),500

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS chat (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, prompt TEXT, response TEXT)")
        c.commit()

def load(user):
    with db() as c:
        return c.execute("SELECT prompt, response FROM chat WHERE user=? ORDER BY id DESC LIMIT 10", (user,)).fetchall()[::-1]

def save(user, prompt, response):
    with db() as c:
        c.execute("INSERT INTO chat (user, prompt, response) VALUES (?, ?, ?)", (user, prompt, response))
        c.commit()

def last_prompt(user):
    with db() as c:
        row = c.execute("SELECT prompt FROM chat WHERE user=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
        return row["prompt"] if row else None

def response_json(status, code, message, data=None, error=None):
    return jsonify({"status": status, "message": message, "data": data, "error": error}), code




@app.route("/")
def home():
    return """<!DOCTYPE html>
<html>
<head>
<title>Home</title>
<style>
body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#0f172a}
.face{font-size:100px;animation:bounce 1s infinite}
@keyframes bounce{0%{transform:translateY(0)}50%{transform:translateY(-30px)}100%{transform:translateY(0)}}
</style>
</head>
<body>
<div class="face">😄</div>
</body>
</html>"""


@app.route("/api/ai", methods=["POST"])
def ai():
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()

        user = data.get("user")
        prompt = data.get("prompt")
        is_doc = data.get("is_doc")
        file_url = data.get("file_url")

        if not user or not is_doc:
            return response_json("error", 400, "Invalid input", error={"type": "ValidationError", "details": ["Missing user or is_doc"]})

        if is_doc in ["img", "aud", "vid"] and not prompt:
            prompt = last_prompt(user)
            if not prompt:
                return response_json("error", 400, "No context found", error={"type": "ContextError", "details": ["No previous prompt"]})

        if is_doc == "text" and not prompt:
            return response_json("error", 400, "Prompt required", error={"type": "ValidationError", "details": ["Empty prompt"]})

        mime = {"img": "image/jpeg", "aud": "audio/mpeg", "vid": "video/mp4"}

        history = load(user)
        contents = [{"role": "user", "parts": [{"text": brain}]}]

        for h in history:
            contents.append({"role": "user", "parts": [{"text": h["prompt"]}]})
            contents.append({"role": "model", "parts": [{"text": h["response"]}]})

        parts = [{"text": prompt}]

        if is_doc in ["img", "aud", "vid"]:
            if not file_url:
                return response_json("error", 400, "file_url required", error={"type": "ValidationError", "details": ["Missing file_url"]})

            parts.append({"file_data": {"mime_type": mime[is_doc], "file_uri": file_url}})

        contents.append({"role": "user", "parts": parts})

        payload = {"contents": contents}

        ai = requests.post(GEMINI_URL, headers=HEADERS, json=payload, timeout=60)

        if ai.status_code != 200:
            err = ai.json().get("error", {})
            return response_json("error", ai.status_code, "AI error", error={"type": err.get("status"), "details": [err.get("message")]})

        answer = ai.json()["candidates"][0]["content"]["parts"][0]["text"]

        save(user, prompt, answer)

        return response_json("success", 200, "ok", data={"response": answer})

    except Exception as e:
        return response_json("error", 500, "server error", error={"type": "Exception", "details": [str(e)]})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
