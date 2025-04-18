# main.py
import json
import threading
import os
import logging
from logging.handlers import RotatingFileHandler
from api import app
from database import init_db
from udp import start_udp_listener
from query import start_scheduled_getinfo, start_scheduled_sync

# Logging konfigurieren
os.makedirs("logs", exist_ok=True)

# Info- und allgemeine Logs
info_handler = RotatingFileHandler("logs/server.log", maxBytes=5*1024*1024, backupCount=2)
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Fehler-Logs separat
error_handler = RotatingFileHandler("logs/error.log", maxBytes=5*1024*1024, backupCount=2)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Konsole
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[info_handler, error_handler, console_handler])

# Konfiguration laden
with open("config.json") as f:
    config = json.load(f)

init_db()

threading.Thread(target=start_udp_listener, daemon=True).start()
threading.Thread(target=start_scheduled_getinfo, daemon=True).start()
threading.Thread(target=start_scheduled_sync, daemon=True).start()

# Flask starten
if config.get("use_ssl"):
    app.run(
        host=config.get("host", "0.0.0.0"),
        port=config.get("port", 5000),
        ssl_context=(config["ssl_cert"], config["ssl_key"])
    )
else:
    app.run(
        host=config.get("host", "0.0.0.0"),
        port=config.get("port", 5000)
    )
