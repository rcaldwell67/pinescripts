import requests
import os


REMOTE_URL = "https://raw.githubusercontent.com/rcaldwell67/pinescripts/main/backend/data/tradingcopilot.db"
LOCAL_PATHS = [
    os.path.join(os.path.dirname(__file__), "tradingcopilot.db"),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db')),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db')),
]

def download_db():
    print(f"Downloading from {REMOTE_URL} ...")
    resp = requests.get(REMOTE_URL)
    resp.raise_for_status()
    for path in LOCAL_PATHS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(resp.content)
        print(f"Database updated at {path}")

def main():
    download_db()

if __name__ == "__main__":
    main()
