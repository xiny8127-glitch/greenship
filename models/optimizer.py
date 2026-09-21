"""基于 SciPy 差分进化算法的分航段航速优化。"""

from __future__ import annotations

import numpy as np
from scipy.optimize import differential_evolution

from models.energy_model import DEFAULTS, number, power_at_speed


def segment_energy(speed: float, distance: float, current: float, depth: float, payload: dict) -> tuple[float, float]:
    ground_speed = max(speed + current, 0.5)
    duration = distance / ground_speed
    energy = (power_at_speed(speed, payload, current, depth) + 8.0) * duration * 1.06
    return energy, duration


def optimize_route(payload: dict) -> dict:
    p = {**DEFAULTS, **payload}
    n = int(number(p, "segments"))
    total_distance = number(p, "distance")
    segment_distances = payload.get("segment_distances")
    if not isinstance(segment_distances, list) or len(segment_distances) != n:
        segment_distances = [total_distance / n] * n
    else:
        scale = total_distance / max(sum(float(x) for x in segment_distances), 0.001)
        segment_distances = [float(x) * scale for x in segment_distances]

    base_current = abs(number(p, "current_speed"))
    sign = 1 if p.get("current_direction") == "downstream" else -1
    currents = payload.get("segment_currents")
    if not isinstance(currents, list) or len(currents) != n:
        variation = np.linspace(-0.18, 0.18, n)
        currents = [sign * max(0, base_current + float(x)) for x in variation]
    else:
        currents = [float(x) for x in currents]
    depths = payload.get("segment_depths")
    if not isinstance(depths, list) or len(depths) != n:
        depth = number(p, "water_depth")
        depths = [max(1.2, depth + 0.35 * np.sin(i * 1.7)) for i in range(n)]
    else:
        depths = [float(x) for x in depths]

    min_speed, max_speed = 6.0, 14.0
    fixed_speed = min(max(number(p, "speed"), min_speed), max_speed)
    max_time = float(payload.get("max_time") or total_distance / max(fixed_speed + sign * base_current, 0.5) * 1.08)
    battery_available = number(p, "battery_capacity") * (number(p, "soc_initial") - number(p, "soc_min")) / 100

    def totals(speeds):
        pairs = [segment_energy(float(speeds[i]), segment_distances[i], currents[i], depths[i], p) for i in range(n)]
        return sum(x[0] for x in pairs), sum(x[1] for x in pairs)

    fixed = [fixed_speed] * n
    # 规则策略：逆流/浅水段降速，顺流/深水段适当提速。
    rule = [float(np.clip(fixed_speed + currents[i] * 0.65 + (depths[i] - number(p, "water_depth")) * 0.25, min_speed, max_speed)) for i in range(n)]
    fixed_energy, fixed_time = totals(fixed)
    rule_energy, rule_time = totals(rule)

    def objective(speeds):
        energy, duration = totals(speeds)
        time_penalty = max(0.0, duration - max_time) ** 2 * 25000
        battery_penalty = max(0.0, energy - battery_available) ** 2 * 1500
        return energy + time_penalty + battery_penalty

    result = differential_evolution(objective, [(min_speed, max_speed)] * n, seed=42, popsize=10, maxiter=100, tol=1e-7, polish=True, workers=1)
    ai = [round(float(v), 2) for v in result.x]
    ai_energy, ai_time = totals(ai)
    saving = (fixed_energy - ai_energy) / fixed_energy * 100 if fixed_energy else 0
    remaining_soc = number(p, "soc_initial") - ai_energy / max(number(p, "battery_capacity"), 0.001) * 100

    return {
        "segments": [{"index": i + 1, "distance": round(segment_distances[i], 2), "current": round(currents[i], 2), "depth": round(depths[i], 2), "fixed_speed": round(fixed[i], 2), "rule_speed": round(rule[i], 2), "ai_speed": ai[i]} for i in range(n)],
        "strategies": {
            "fixed": {"energy": round(fixed_energy, 2), "time": round(fixed_time, 2)},
            "rule": {"energy": round(rule_energy, 2), "time": round(rule_time, 2)},
            "ai": {"energy": round(ai_energy, 2), "time": round(ai_time, 2)},
        },
        "saving_rate": round(saving, 2), "remaining_soc": round(remaining_soc, 1),
        "constraints": {"max_time": round(max_time, 2), "battery_available": round(battery_available, 2), "time_satisfied": bool(ai_time <= max_time + 0.01), "battery_satisfied": bool(ai_energy <= battery_available + 0.01)},
        "success": bool(result.success), "algorithm": "SciPy Differential Evolution",
    }
