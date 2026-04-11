import requests
import os

REMOTE_URL = "https://raw.githubusercontent.com/rcaldwell67/pinescripts/main/backend/data/tradingcopilot.db"
LOCAL_PATH = os.path.join(os.path.dirname(__file__), "tradingcopilot.db")

def download_db():
    print(f"Downloading from {REMOTE_URL} ...")
    resp = requests.get(REMOTE_URL)
    resp.raise_for_status()
    with open(LOCAL_PATH, "wb") as f:
        f.write(resp.content)
    print(f"Database updated at {LOCAL_PATH}")

def main():
    download_db()

if __name__ == "__main__":
    main()
