# api.py
from flask import Flask, jsonify
from flask_cors import CORS
from database import get_db

app = Flask(__name__)
CORS(app)

@app.route("/servers", methods=["GET"])
def get_servers():
    """ Gibt die aktuelle Serverliste als JSON zurück. """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ip, port, name, version, mod, players, max_players, map, first_seen, last_heartbeat
            FROM servers WHERE last_heartbeat >= datetime('now', '-19 minutes')
        """)
        servers = cursor.fetchall()

    return jsonify([
        {
            "ip": row[0],
            "port": row[1],
            "name": row[2] if row[2] else "Unknown",
            "version": row[3] if row[3] else "Unknown",
            "mod": row[4] if row[4] else "Unknown",
            "players": row[5] if row[5] is not None else 0,
            "max_players": row[6] if row[6] is not None else 0,
            "map": row[7] if row[7] else "Unknown",
            "first_seen": row[8],
            "last_heartbeat": row[9]
        } for row in servers
    ])
