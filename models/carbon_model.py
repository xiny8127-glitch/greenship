"""碳排放计算。排放因子集中管理，便于更新研究口径。"""

EMISSION_FACTORS = {
    "diesel_kg_per_l": 2.63,
    "electricity_kg_per_kwh": 0.5703,
}


def diesel_emission(litres: float) -> float:
    return litres * EMISSION_FACTORS["diesel_kg_per_l"]


def electric_emission(kwh: float) -> float:
    return kwh * EMISSION_FACTORS["electricity_kg_per_kwh"]
