# query.py
import socket
import time
import struct
import threading
import logging
import concurrent.futures
import json
from database import get_db

# Konfiguration laden
with open("config.json") as f:
    config = json.load(f)

# Globale Zeitstempel
last_query_time = {}
last_heartbeat_time = {}
lock = threading.Lock()

# Konfiguration auslesen
KNOWN_PROTOCOLS = config.get("known_protocols", [84])
MASTER_SERVERS = config.get("master_servers", [])

def query_server(ip, port):
    try:
        request = b"\xFF\xFF\xFF\xFFgetinfo 0"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.sendto(request, (ip, port))
        response, _ = sock.recvfrom(4096)
        sock.close()
        data = response.decode("latin-1", errors="ignore").strip()
        if "infoResponse" in data:
            return parse_info_response(data)
    except Exception as e:
        logging.warning(f"Fehler beim Abrufen von {ip}:{port}: {e}")
    return None

def parse_info_response(data):
    try:
        data = data.split("\\")[1:]
        info = {data[i]: data[i + 1] for i in range(0, len(data) - 1, 2)}
        version = info.get("version")
        if not version and info.get("protocol") == "84":
            version = "ET 2.60b linux-i386 May 8 2006"
        elif not version:
            version = "Unknown"
        return {
            "name": info.get("hostname", "Unknown"),
            "version": version,
            "mod": info.get("game", "Unknown"),
            "players": int(info.get("clients", 0)),
            "max_players": int(info.get("sv_maxclients", 0)),
            "map": info.get("mapname", "Unknown"),
        }
    except Exception as e:
        logging.exception(f"Fehler beim Parsen der Serverantwort: {e}")
    return None

def update_server_info(ip, port):
    server_info = query_server(ip, port)
    if server_info:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE servers SET 
                    name=?, version=?, mod=?, players=?, max_players=?, map=?, last_heartbeat=CURRENT_TIMESTAMP
                    WHERE ip=? AND port=?
                """, (server_info["name"], server_info["version"], server_info["mod"],
                      server_info["players"], server_info["max_players"], server_info["map"], ip, port))
                conn.commit()
        except Exception as e:
            logging.exception(f"Fehler beim Aktualisieren der Serverdaten: {e}")
    with lock:
        last_query_time[(ip, port)] = time.time()

def start_scheduled_getinfo():
    while True:
        current_time = time.time()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ip, port FROM servers")
            servers = cursor.fetchall()

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            futures = []
            for ip, port in servers:
                addr = (ip, port)
                with lock:
                    heartbeat_ok = addr in last_heartbeat_time and (current_time - last_heartbeat_time[addr]) <= 720
                    query_needed = addr not in last_query_time or (current_time - last_query_time[addr]) >= 15
                if heartbeat_ok and query_needed:
                    futures.append(executor.submit(update_server_info, ip, port))
            concurrent.futures.wait(futures)
        time.sleep(5)

def fetch_master_servers(master_host):
    all_servers = set()
    for protocol in KNOWN_PROTOCOLS:
        try:
            request = b"\xFF\xFF\xFF\xFFgetservers " + str(protocol).encode() + b" empty full"
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            sock.sendto(request, (master_host, 27950))
            all_data = b""
            while True:
                try:
                    response, _ = sock.recvfrom(8192)
                    all_data += response
                    if response.endswith(b"\xFF\xFF\xFF\xFF"):
                        break
                except socket.timeout:
                    break
            sock.close()
            if len(all_data) > 24:
                servers = parse_getservers_response(all_data)
                all_servers.update(servers)
                break
        except Exception as e:
            logging.warning(f"Fehler bei {master_host} (Protocol {protocol}): {e}")
    return all_servers

def parse_getservers_response(response):
    servers = set()
    if response.startswith(b"\xFF\xFF\xFF\xFFgetserversResponse"):
        response = response[24:]
    for i in range(0, len(response), 6):
        try:
            ip_bytes = response[i:i+4]
            port_bytes = response[i+4:i+6]
            if len(ip_bytes) == 4 and len(port_bytes) == 2:
                ip = ".".join(str(b) for b in ip_bytes)
                port = struct.unpack(">H", port_bytes)[0]
                servers.add((ip, port))
        except Exception as e:
            logging.warning(f"Fehler beim Parsen eines Servers: {e}")
    return servers

def sync_with_masters():
    all_servers = set()
    for master_host, _ in MASTER_SERVERS:
        servers = fetch_master_servers(master_host)
        all_servers.update(servers)

    with get_db() as conn:
        cursor = conn.cursor()
        for ip, port in all_servers:
            cursor.execute("SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
            row = cursor.fetchone()
            if not row:
                cursor.execute("""
                    INSERT INTO servers (ip, port, name, version, mod, players, max_players, map, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (ip, port, "Unknown", "Unknown", "Unknown", 0, 0, "Unknown"))
        conn.commit()

def start_scheduled_sync():
    while True:
        sync_with_masters()
        time.sleep(300)
