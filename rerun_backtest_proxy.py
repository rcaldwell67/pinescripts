from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # Set this in your environment securely
REPO = "rcaldwell67/pinescripts"

@app.route("/rerun-backtest", methods=["POST"])
def rerun_backtest():
    data = request.json
    symbol = data.get("symbol")
    version = data.get("version")
    if not symbol or not version:
        return jsonify({"ok": False, "error": "Missing symbol or version"}), 400
    url = f"https://api.github.com/repos/{REPO}/dispatches"
    payload = {
        "event_type": "rerun-backtest",
        "client_payload": {"symbol": symbol, "version": version}
    }
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.everest-preview+json"
    }
    resp = requests.post(url, json=payload, headers=headers)
    if resp.ok:
        return jsonify({"ok": True}), 200
    else:
        return jsonify({"ok": False, "error": resp.text}), resp.status_code

if __name__ == "__main__":
    app.run(port=5001, debug=True)
