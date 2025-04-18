# udp.py
import socket
import threading
import logging
import struct
import time
import json
from query import query_server, last_query_time, last_heartbeat_time, lock
from database import get_db

# Konfiguration laden
with open("config.json") as f:
    config = json.load(f)

UDP_IP = config.get("udp_ip", "0.0.0.0")
UDP_PORT = config.get("udp_port", 27950)

def start_udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    logging.info(f"Masterserver läuft auf {UDP_IP}:{UDP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        message = data.decode("latin-1", errors="ignore").strip()
        logging.info(f"Empfangene Anfrage von {addr}: {message}")

        if message.startswith("heartbeat"):
            threading.Thread(target=handle_heartbeat, args=(data, addr)).start()
        elif message.startswith("getservers"):
            threading.Thread(target=handle_getservers, args=(sock, addr)).start()

def handle_heartbeat(data, addr):
    with get_db() as conn:
        cursor = conn.cursor()
        message = data.decode("utf-8", errors="ignore").strip()
        logging.info(f"Heartbeat von {addr}: {message}")

        current_time = time.time()
        with lock:
            if addr in last_query_time and (current_time - last_query_time[addr]) < 15:
                return

        server_info = query_server(addr[0], addr[1])
        if not server_info:
            logging.warning(f"Keine Infos von {addr} abrufbar")
            return

        with lock:
            last_query_time[addr] = current_time
            last_heartbeat_time[addr] = current_time

        cursor.execute("SELECT id FROM servers WHERE ip = ? AND port = ?", (addr[0], addr[1]))
        row = cursor.fetchone()

        if row:
            cursor.execute("""
                UPDATE servers SET 
                name=?, version=?, mod=?, players=?, max_players=?, map=?, last_heartbeat=CURRENT_TIMESTAMP
                WHERE ip=? AND port=?
            """, (server_info["name"], server_info["version"], server_info["mod"],
                  server_info["players"], server_info["max_players"], server_info["map"],
                  addr[0], addr[1]))
        else:
            cursor.execute("""
                INSERT INTO servers (ip, port, name, version, mod, players, max_players, map)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (addr[0], addr[1], server_info["name"], server_info["version"],
                  server_info["mod"], server_info["players"], server_info["max_players"], server_info["map"]))

        conn.commit()

def handle_getservers(sock, addr):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ip, port FROM servers WHERE last_heartbeat >= datetime('now', '-6 minutes')")
        servers = cursor.fetchall()

    if not servers:
        logging.info(f"Keine Server für getserversResponse an {addr}")
        return

    logging.info(f"Sende {len(servers)} Server an {addr}")

    response = b"\xFF\xFF\xFF\xFFgetserversResponse"
    for ip, port in servers:
        try:
            ip_bytes = bytes(map(int, ip.split(".")))
            port_bytes = struct.pack(">H", port)
            response += ip_bytes + port_bytes
        except Exception as e:
            logging.warning(f"Fehler beim Kodieren von {ip}:{port}: {e}")

    response += b"\xFF\xFF\xFF\xFF"

    try:
        sock.sendto(response, addr)
    except Exception as e:
        logging.warning(f"Fehler beim Senden an {addr}: {e}")