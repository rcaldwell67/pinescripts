DELETE FILE

"""
Generates v7 Pine Script and Python strategy files for all symbols in the MariaDB symbols table.
"""
import os
import mariadb
from jinja2 import Template
from dotenv import load_dotenv

# --- LOAD ENV ---
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# --- CONFIG ---
DB_CONFIG = {
    "user": os.environ.get("MARIADB_USER", "root"),
    "password": os.environ.get("MARIADB_PASSWORD", ""),
    "host": os.environ.get("MARIADB_HOST", "localhost"),
    "port": int(os.environ.get("MARIADB_PORT", 3306)),
    "database": os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
}
PINE_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../pine_templates/APM v7-TEMPLATE.pine")
PY_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "v7/apm_v7.py")
PINE_OUT_DIR = os.path.join(os.path.dirname(__file__), "../pine_templates")
PY_OUT_DIR = os.path.join(os.path.dirname(__file__), "v7")

def load_template(path):
    with open(path, "r") as f:
        return Template(f.read())

pine_template = load_template(PINE_TEMPLATE_PATH)
py_template = load_template(PY_TEMPLATE_PATH)

def get_symbols():
    conn = mariadb.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM symbols WHERE isactive=1")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return symbols

def symbol_to_filename(symbol):
    return symbol.replace("/", "").replace("-", "").upper()

def generate_pine(symbol):
    fname = f"APM v7-{symbol_to_filename(symbol)}-ALL.pine"
    out_path = os.path.join(PINE_OUT_DIR, fname)
    with open(out_path, "w") as f:
        f.write(pine_template.render(symbol=symbol))
    print(f"Wrote {out_path}")

def generate_py(symbol):
    fname = f"apm_v7_{symbol_to_filename(symbol)}.py"
    out_path = os.path.join(PY_OUT_DIR, fname)
    with open(out_path, "w") as f:
        f.write(py_template.render(symbol=symbol))
    print(f"Wrote {out_path}")

def main():
    symbols = get_symbols()
    for symbol in symbols:
        generate_pine(symbol)
        generate_py(symbol)
        print(f"[STATUS] v7 scripts generated for {symbol}")

if __name__ == "__main__":
    main()
