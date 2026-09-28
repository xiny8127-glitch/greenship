"""船舶能耗、费用、碳排与绿色指数模型。"""

from __future__ import annotations

from models.carbon_model import EMISSION_FACTORS, diesel_emission, electric_emission

DEFAULTS = {
    "ship_type": "内河集装箱船",
    "cargo_mass": 800.0,
    "distance": 30.0,
    "speed": 10.0,
    "propulsion_power": 95.0,
    "battery_capacity": 520.0,
    "soc_initial": 90.0,
    "soc_min": 20.0,
    "diesel_consumption": 4,
    "hybrid_diesel_ratio": 35.0,
    "current_speed": 1,
    "current_direction": "downstream",
    "water_depth": 4.0,
    "design_cargo": 1000.0,
    "segments": 6,
    "electricity_type": "shore",
}


def number(payload: dict, key: str) -> float:
    try:
        return float(payload.get(key, DEFAULTS.get(key, 0)))
    except (TypeError, ValueError):
        raise ValueError(f"{key} 必须是有效数字")


def validate_payload(payload: dict, optimization: bool = False) -> list[str]:
    labels = {
        "cargo_mass": "载货量", "speed": "航速",
        "propulsion_power": "推进功率", "battery_capacity": "电池容量",
        "soc_initial": "当前 SOC", "soc_min": "最低 SOC",
        "diesel_consumption": "柴油单位航程消耗", "hybrid_diesel_ratio": "混合动力柴油占比",
        "water_depth": "水深", "segments": "航段数量",
    }
    errors = []
    values = {}
    for key in labels:
        try:
            values[key] = number(payload, key)
        except ValueError:
            errors.append(f"{labels[key]}必须是有效数字")
    if errors:
        return errors
    integer_labels = {
        "cargo_mass": "载货量", "distance": "航程", "speed": "航速",
        "propulsion_power": "推进功率", "battery_capacity": "电池容量",
        "soc_initial": "当前 SOC", "soc_min": "最低 SOC",
        "diesel_consumption": "柴油单位航程消耗",
        "hybrid_diesel_ratio": "混合动力柴油占比", "water_depth": "水深",
        "segments": "航段数量", "current_speed": "水流速度",
    }
    if optimization:
        integer_labels["design_cargo"] = "设计载重"
        if payload.get("max_time") not in (None, ""):
            integer_labels["max_time"] = "最大时间"
    for key, label in integer_labels.items():
        try:
            value = number(payload, key) if key != "max_time" else float(payload[key])
            if not value.is_integer():
                errors.append(f"{label}只支持整数")
        except (TypeError, ValueError):
            errors.append(f"{label}必须是有效整数")
    if errors:
        return errors
    for key in ("distance", "speed", "water_depth"):
        if values[key] <= 0:
            errors.append(f"{labels[key]}必须大于 0")
    for key in ("cargo_mass", "propulsion_power", "battery_capacity", "diesel_consumption"):
        if values[key] < 0:
            errors.append(f"{labels[key]}不能小于 0")
    for key in ("soc_initial", "soc_min", "hybrid_diesel_ratio"):
        if not 0 <= values[key] <= 100:
            errors.append(f"{labels[key]}必须在 0–100 之间")
    if values["soc_min"] > values["soc_initial"]:
        errors.append("最低允许 SOC 不能高于当前 SOC")
    if optimization and not 1 <= int(values["segments"]) <= 20:
        errors.append("航段数量必须在 1–20 之间")
    current = abs(number(payload, "current_speed"))
    direction = payload.get("current_direction", DEFAULTS["current_direction"])
    ground_speed = values["speed"] + (current if direction == "downstream" else -current)
    if ground_speed <= 0.5:
        errors.append("当前流速条件下对地航速过低，请提高航速或降低逆流速度")
    return errors


def power_at_speed(speed: float, payload: dict, current_signed: float = 0.0, depth: float | None = None) -> float:
    """立方航速功率模型，加入载重、浅水与逆流修正。"""
    rated = number(payload, "propulsion_power")
    base_speed = max(number(payload, "speed"), 1.0)
    cargo = number(payload, "cargo_mass")
    design_cargo = max(number(payload, "design_cargo"), 1.0)
    actual_depth = depth if depth is not None else number(payload, "water_depth")
    base_load = rated * 0.18
    propulsive = rated * 0.82 * (speed / base_speed) ** 3
    cargo_factor = 0.82 + 0.28 * min(cargo / design_cargo, 1.5)
    shallow_factor = 1 + max(0.0, 4.0 - actual_depth) * 0.035
    current_factor = 1 + max(0.0, -current_signed) * 0.025
    return max(0.0, (base_load + propulsive) * cargo_factor * shallow_factor * current_factor)


def electric_energy(payload: dict) -> tuple[float, float, float]:
    speed = number(payload, "speed")
    current = abs(number(payload, "current_speed"))
    signed = current if payload.get("current_direction", "downstream") == "downstream" else -current
    ground_speed = max(speed + signed, 0.5)
    time = number(payload, "distance") / ground_speed
    power = power_at_speed(speed, payload, signed)
    hotel_load = 8.0
    energy = (power + hotel_load) * time * 1.06  # 传动与电池损耗
    return energy, time, power


def calculate_all_schemes(payload: dict, prices: dict) -> dict:
    p = {**DEFAULTS, **payload}
    distance = number(p, "distance")
    cargo = max(number(p, "cargo_mass"), 0.001)
    energy, travel_time, effective_power = electric_energy(p)
    diesel_l = number(p, "diesel_consumption") * distance
    ratio = number(p, "hybrid_diesel_ratio") / 100
    electricity_price = prices["shore_electricity"] if p.get("electricity_type") == "shore" else prices["industrial_electricity"]

    variants = {
        "diesel": (diesel_l, 0.0),
        "electric": (0.0, energy),
        "hybrid": (diesel_l * ratio, energy * (1 - ratio)),
    }
    schemes = {}
    for key, (fuel, kwh) in variants.items():
        cost = fuel * prices["diesel"] + kwh * electricity_price
        co2 = diesel_emission(fuel) + electric_emission(kwh)
        equivalent_energy = kwh + fuel * 9.9
        schemes[key] = {
            "key": key, "travel_time": round(travel_time, 2),
            "diesel_l": round(fuel, 2), "electricity_kwh": round(kwh, 2),
            "energy_label": f"{fuel:.1f} L" if key == "diesel" else (f"{kwh:.1f} kWh" if key == "electric" else f"{fuel:.1f} L + {kwh:.1f} kWh"),
            "cost": round(cost, 2), "co2": round(co2, 2),
            "cost_per_km": round(cost / distance, 3),
            "transport_cost": round(cost / (cargo * distance), 5),
            "transport_energy": round(equivalent_energy / (cargo * distance), 5),
            "new_energy_ratio": round((kwh / equivalent_energy * 100) if equivalent_energy else 0, 1),
        }

    diesel = schemes["diesel"]
    battery = number(p, "battery_capacity")
    available = battery * (number(p, "soc_initial") - number(p, "soc_min")) / 100
    remaining_kwh = battery * number(p, "soc_initial") / 100 - energy
    remaining_soc = remaining_kwh / battery * 100 if battery else -1
    battery_safe = battery > 0 and remaining_soc >= number(p, "soc_min")

    for key, scheme in schemes.items():
        scheme["co2_reduction"] = round(diesel["co2"] - scheme["co2"], 2)
        scheme["reduction_rate"] = round((diesel["co2"] - scheme["co2"]) / diesel["co2"] * 100, 1) if diesel["co2"] else 0
        scheme["cost_saving"] = round(diesel["cost"] - scheme["cost"], 2)
        scheme["cost_reduction_rate"] = round((diesel["cost"] - scheme["cost"]) / diesel["cost"] * 100, 1) if diesel["cost"] else 0

    # 多指标归一化评价；纯电不可达时施加安全惩罚。
    max_cost = max(x["cost"] for x in schemes.values()) or 1
    max_co2 = max(x["co2"] for x in schemes.values()) or 1
    max_energy = max(x["transport_energy"] for x in schemes.values()) or 1
    for key, scheme in schemes.items():
        battery_factor = 1.0
        if key == "electric" and not battery_safe:
            battery_factor = 0.15
        elif key == "hybrid":
            hybrid_use = energy * (1 - ratio)
            hybrid_remaining = battery * number(p, "soc_initial") / 100 - hybrid_use
            if battery <= 0 or hybrid_remaining / max(battery, 0.001) * 100 < number(p, "soc_min"):
                battery_factor = 0.45
        raw = (1 - scheme["co2"] / max_co2) * 35 + (1 - scheme["cost"] / max_cost) * 25 + (1 - scheme["transport_energy"] / max_energy) * 15 + scheme["new_energy_ratio"] / 100 * 15 + battery_factor * 10
        scheme["green_score"] = round(max(0, min(100, 35 + raw)), 0)
        scheme["rating"] = "优秀" if scheme["green_score"] >= 85 else "良好" if scheme["green_score"] >= 70 else "一般" if scheme["green_score"] >= 55 else "待改善"

    feasible = {k: v for k, v in schemes.items() if not (k == "electric" and not battery_safe)}
    recommended_key = max(feasible, key=lambda k: feasible[k]["green_score"])
    rec = schemes[recommended_key]
    names = {"diesel": "传统柴油动力", "electric": "纯电动力", "hybrid": "柴油 + 电池混合动力"}
    reasons = [f"综合绿色指数达到 {int(rec['green_score'])} 分", f"CO₂ 较柴油方案降低 {rec['reduction_rate']:.1f}%", f"能源成本较柴油方案降低 {rec['cost_reduction_rate']:.1f}%"]
    reasons.append("剩余 SOC 满足安全要求" if battery_safe or recommended_key == "diesel" else "当前电池余量更适合采用混合动力")

    return {
        "schemes": schemes,
        "recommended": {"key": recommended_key, "name": names[recommended_key], "reasons": reasons},
        "battery": {
            "consumption": round(energy, 2), "available": round(available, 2),
            "remaining_kwh": round(remaining_kwh, 2), "remaining_soc": round(remaining_soc, 1),
            "safe": battery_safe,
            "message": "当前电池容量满足本次航行需求。" if battery_safe else "当前方案存在续航风险",
            "suggestions": [] if battery_safe else ["降低航速", "增加充电", "使用混合动力", "调整航行计划"],
        },
        "summary": {"travel_time": round(travel_time, 2), "effective_power": round(effective_power, 1), "electricity_price": electricity_price},
        "config": {"emission_factors": EMISSION_FACTORS},
    }
