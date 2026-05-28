import math
import os
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

CITY_META = [
    {"id": "jakarta",  "name": "Jakarta",  "lat": -6.2088, "lon": 106.8456, "base": 95},
    {"id": "bandung",  "name": "Bandung",  "lat": -6.9175, "lon": 107.6191, "base": 55},
    {"id": "surabaya", "name": "Surabaya", "lat": -7.2575, "lon": 112.7521, "base": 80},
    {"id": "medan",    "name": "Medan",    "lat":  3.5952, "lon":  98.6722, "base": 70},
    {"id": "denpasar", "name": "Denpasar", "lat": -8.6705, "lon": 115.2126, "base": 45},
]
CITIES = {c["id"]: c for c in CITY_META}

APP_TITLE = os.environ.get("APP_TITLE", "Air Quality Monitor")
APP_SUBTITLE = os.environ.get("APP_SUBTITLE", "Pemantauan kualitas udara real-time")
DEFAULT_CITY = os.environ.get("DEFAULT_CITY", "jakarta")
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "5000"))

overrides = {}

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def aqi_at(meta, ts):
    base = meta["base"]
    phase = (sum(ord(ch) for ch in meta["id"]) % 100) / 100 * 2 * math.pi
    t_h = ts / 3600.0
    value = (
        base
        + 18 * math.sin(2 * math.pi * t_h / 24 + phase)
        + 8 * math.sin(2 * math.pi * t_h / 6 + phase * 1.7)
        + 6 * math.sin(2 * math.pi * t_h / 0.1 + phase * 0.5)
    )
    return int(clamp(round(value), 8, 190))

def aqi_to_pm25(aqi):
    return round(aqi * 0.45, 1)

def get_status(aqi):
    if aqi <= 50: return "Baik"
    elif aqi <= 100: return "Sedang"
    elif aqi <= 150: return "Tidak Sehat untuk Kelompok Sensitif"
    elif aqi <= 200: return "Tidak Sehat"
    else: return "Berbahaya"

def get_advice(aqi):
    if aqi <= 50:
        return "Kualitas udara baik. Nikmati aktivitas di luar ruangan."
    elif aqi <= 100:
        return "Masih dapat diterima. Kelompok sensitif sebaiknya kurangi aktivitas berat di luar."
    elif aqi <= 150:
        return "Kelompok sensitif (anak, lansia, penderita asma) batasi aktivitas luar ruangan."
    elif aqi <= 200:
        return "Kurangi aktivitas di luar ruangan dan gunakan masker bila perlu."
    else:
        return "Hindari aktivitas di luar ruangan. Tetap di dalam dan tutup ventilasi."

def snapshot(meta):
    ov = overrides.get(meta["id"])
    if ov:
        aqi, pm25 = ov["aqi"], ov["pm25"]
    else:
        aqi = aqi_at(meta, time.time())
        pm25 = aqi_to_pm25(aqi)
    return {
        "id": meta["id"], "location": meta["name"],
        "lat": meta["lat"], "lon": meta["lon"],
        "aqi": aqi, "pm25": pm25,
        "status": get_status(aqi), "advice": get_advice(aqi),
    }

def history_for(meta):
    now = int(time.time())
    hour_start = now - (now % 3600)
    points = []
    for hours_ago in range(23, -1, -1):
        ts = hour_start - hours_ago * 3600
        points.append({
            "time": datetime.fromtimestamp(ts).strftime("%H:%M"),
            "aqi": aqi_at(meta, ts),
        })
    return points

@app.route('/')
def index():
    city_id = DEFAULT_CITY if DEFAULT_CITY in CITIES else "jakarta"
    return render_template(
        'index.html',
        data=snapshot(CITIES[city_id]),
        app_title=APP_TITLE,
        app_subtitle=APP_SUBTITLE,
        default_city=city_id,
        refresh_interval=REFRESH_INTERVAL,
    )

@app.route('/api/cities')
def get_cities():
    data = []
    for meta in CITY_META:
        s = snapshot(meta)
        data.append({"id": s["id"], "name": s["location"], "lat": s["lat"],
                     "lon": s["lon"], "aqi": s["aqi"], "status": s["status"]})
    return jsonify(data)

@app.route('/api/data')
def get_data():
    meta = CITIES.get(request.args.get('city', 'jakarta'))
    if not meta:
        return jsonify({"error": "Kota tidak ditemukan"}), 404
    return jsonify(snapshot(meta))

@app.route('/api/history')
def get_history():
    meta = CITIES.get(request.args.get('city', 'jakarta'))
    if not meta:
        return jsonify({"error": "Kota tidak ditemukan"}), 404
    return jsonify({"city": meta["name"], "history": history_for(meta)})


@app.route('/api/update', methods=['POST'])
def update_data():
    req = request.get_json(silent=True) or {}
    meta = CITIES.get(req.get('city', 'jakarta'))
    if meta and 'aqi' in req:
        aqi = int(clamp(req['aqi'], 0, 500))
        overrides[meta["id"]] = {"aqi": aqi, "pm25": req.get('pm25', aqi_to_pm25(aqi))}
        return jsonify({"message": "Data berhasil diupdate", "data": snapshot(meta)}), 200
    return jsonify({"error": "Data tidak valid"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
