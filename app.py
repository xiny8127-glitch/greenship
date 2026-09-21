from __future__ import annotations

import csv
import io
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from models.energy_model import calculate_all_schemes, validate_payload
from models.optimizer import optimize_route


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOYAGES_FILE = DATA_DIR / "voyages.json"
DATA_LOCK = threading.Lock()

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


ENERGY_PRICES = {
    "diesel": 7.35,
    "industrial_electricity": 0.82,
    "shore_electricity": 0.68,
    "updated_at": "2026-09-21 18:00",
    "source": "模拟市场数据",
}


def read_voyages() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not VOYAGES_FILE.exists():
        VOYAGES_FILE.write_text("[]", encoding="utf-8")
    try:
        return json.loads(VOYAGES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_voyages(voyages: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = VOYAGES_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(voyages, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(VOYAGES_FILE)


@app.get("/")
def index():
    return render_template("index.html", active="dashboard")


@app.get("/optimization")
def optimization_page():
    return render_template("optimization.html", active="optimization")


@app.get("/history")
def history_page():
    return render_template("history.html", active="history")


@app.get("/about")
def about_page():
    return render_template("about.html", active="about")


@app.get("/api/energy-prices")
def energy_prices():
    return jsonify({"success": True, "data": ENERGY_PRICES})


@app.post("/api/calculate")
def calculate():
    payload = request.get_json(silent=True) or {}
    errors = validate_payload(payload)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400
    try:
        result = calculate_all_schemes(payload, ENERGY_PRICES)
        return jsonify({"success": True, "data": result})
    except (ValueError, TypeError) as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 400


@app.post("/api/optimize")
def optimize():
    payload = request.get_json(silent=True) or {}
    errors = validate_payload(payload, optimization=True)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400
    try:
        result = optimize_route(payload)
        return jsonify({"success": True, "data": result})
    except (ValueError, TypeError) as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 400


@app.post("/api/save-voyage")
def save_voyage():
    payload = request.get_json(silent=True) or {}
    required = ["ship_type", "distance", "speed", "scheme", "energy", "cost", "co2", "green_score"]
    if any(key not in payload for key in required):
        return jsonify({"success": False, "message": "记录信息不完整，请先完成一次计算。"}), 400
    record = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **{key: payload[key] for key in required},
    }
    with DATA_LOCK:
        voyages = read_voyages()
        voyages.insert(0, record)
        write_voyages(voyages[:500])
    return jsonify({"success": True, "message": "本次航行已保存", "data": record})


@app.get("/api/history")
def history():
    with DATA_LOCK:
        voyages = read_voyages()
    return jsonify({"success": True, "data": voyages})


@app.get("/api/export/csv")
def export_csv():
    with DATA_LOCK:
        voyages = read_voyages()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["日期", "船舶类型", "航程(km)", "航速(km/h)", "能源方案", "能源消耗", "费用(元)", "CO₂(kg)", "绿色指数"])
    for item in voyages:
        writer.writerow([item.get(k, "") for k in ("date", "ship_type", "distance", "speed", "scheme", "energy", "cost", "co2", "green_score")])
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=greenship_voyages.csv"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
