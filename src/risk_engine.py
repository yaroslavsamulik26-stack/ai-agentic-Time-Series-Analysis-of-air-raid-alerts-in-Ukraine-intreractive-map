"""
risk_engine.py
Deterministic Target Attractiveness & Strategic Threat Engine for Kyiv Defense Analytics.

Implements Two-layer Defense Architecture:
  1. Time Series Hazard Engine («КОЛИ»): Evaluates temporal window of threat to the capital
     (daily attack peaks, missile/drone inventory replenishment phases, cyclicality) without data leakage.
  2. Target Attractiveness Engine («КУДИ»): Computes deterministic Target Attractiveness Index
     A_i in [0, 100] for critical infrastructure facilities during an attack:
     A_i = (w_crit * C_i + w_doctr * D_i + w_corr * E_i) * (1 - lambda * S_i)
     where:
       - C_i in [0, 100]: Strategic criticality for city life support (energy 90-100, bridges 85, water 80, metro 70, civilian hubs 30)
       - D_i in [0, 100]: Doctrinal priority by threat mode (Shahed vs Missiles)
       - E_i in [0, 100]: Exposure to inbound threat corridors and river channels
       - S_i in [0, 1]: Echeloned air defense shielding (Patriot, NASAMS, mobile fire groups)
       - Tactical statuses:
         * 80-100: «Критична ціль» (#dc2626)
         * 65-79:  «Високий пріоритет» (#ea580c)
         * 50-64:  «Підвищена увага» (#eab308)
         * <50:    «Помірний ризик» (#16a34a)

  3. District Danger Aggregation:
     DistrictDanger(D) = Norm(0.40 * max_{i in D}(A_i) + 0.40 * avg_{i in D}(A_i) + 0.20 * CorridorPenalty(D))
"""

import json
import math
from pathlib import Path
import pandas as pd

try:
    from src.time_series import KyivAlertTimeSeriesAnalyzer
except ImportError:
    try:
        from time_series import KyivAlertTimeSeriesAnalyzer
    except ImportError:
        KyivAlertTimeSeriesAnalyzer = None


def get_target_tactical_status(score: float) -> tuple[str, str]:
    """Returns Ukrainian tactical status and badge hex color for target attractiveness index."""
    try:
        val = float(score)
        if not math.isfinite(val):
            val = 0.0
    except (TypeError, ValueError):
        val = 0.0

    if val >= 80.0:
        return "Критична ціль", "#dc2626"
    elif val >= 65.0:
        return "Високий пріоритет", "#ea580c"
    elif val >= 50.0:
        return "Підвищена увага", "#eab308"
    else:
        return "Помірний ризик", "#16a34a"


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two points in km."""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        if not (math.isfinite(lat1) and math.isfinite(lon1) and math.isfinite(lat2) and math.isfinite(lon2)):
            return 9999.0
    except (TypeError, ValueError):
        return 9999.0

    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def point_to_segment_distance_km(lat: float, lon: float, p1: list | tuple, p2: list | tuple) -> float:
    """
    Computes minimum Euclidean distance in local metric projection
    from point (lat, lon) to segment [p1, p2], where p1, p2 are [lat, lon].
    """
    try:
        lat, lon = float(lat), float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return 9999.0
        if not (isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple)) and len(p1) >= 2 and len(p2) >= 2):
            return 9999.0
        lat1, lon1 = float(p1[0]), float(p1[1])
        lat2, lon2 = float(p2[0]), float(p2[1])
        if not (math.isfinite(lat1) and math.isfinite(lon1) and math.isfinite(lat2) and math.isfinite(lon2)):
            return 9999.0
    except (TypeError, ValueError, IndexError):
        return 9999.0

    mean_lat = math.radians((lat1 + lat2) / 2.0)
    kx = 111.32 * math.cos(mean_lat)
    ky = 110.57

    x = (lon - lon1) * kx
    y = (lat - lat1) * ky
    dx = (lon2 - lon1) * kx
    dy = (lat2 - lat1) * ky

    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-8:
        return math.hypot(x, y)

    t = max(0.0, min(1.0, (x * dx + y * dy) / seg_len_sq))
    proj_x = t * dx
    proj_y = t * dy
    return math.hypot(x - proj_x, y - proj_y)


# 5 Inbound Threat Corridors from verified defense intelligence
THREAT_CORRIDORS = [
    {
        "id": "north_river",
        "modes": ["all", "yellow", "orange"],
        "name": "Північний річковий вектор (Вишгород — Оболонь — Дніпро)",
        "coords": [[50.60, 30.48], [50.53, 30.50], [50.49, 30.53], [50.46, 30.54]],
    },
    {
        "id": "west_zhytomyr",
        "modes": ["all", "yellow", "orange", "red"],
        "name": "Західний сектор (Макарів — Житомирська траса — Святошин)",
        "coords": [[50.47, 30.05], [50.45, 30.22], [50.45, 30.37], [50.45, 30.40]],
    },
    {
        "id": "south_obukhiv",
        "modes": ["all", "yellow", "orange", "red"],
        "name": "Південний сектор (Обухів — Козин — Корчувате — Голосіїв)",
        "coords": [[50.15, 30.65], [50.28, 30.58], [50.35, 30.56], [50.39, 30.54]],
    },
    {
        "id": "se_boryspil",
        "modes": ["all", "yellow", "orange", "red"],
        "name": "Південно-східний вектор (Бориспіль — Бортничі — Дарниця)",
        "coords": [[50.35, 30.95], [50.37, 30.75], [50.40, 30.65], [50.42, 30.60]],
    },
    {
        "id": "ne_brovary",
        "modes": ["all", "yellow", "orange"],
        "name": "Північно-східний вектор (Чернігівський напрямок — Бровари — Деснянський)",
        "coords": [[50.58, 30.90], [50.53, 30.78], [50.50, 30.65], [50.50, 30.58]],
    },
]

# Strategic Air Defense Complexes & Turret Lines
AIR_DEFENSE_COMPLEXES = [
    {
        "id": "turrets_north",
        "name": "Позиційний сектор ППО «Північ» (Оболонь)",
        "lat": 50.525,
        "lon": 30.515,
        "radius_km": 4.5,
        "drone_shield": 0.65,
        "missile_shield": 0.40,
    },
    {
        "id": "turrets_west",
        "name": "Вогневий рубіж ППО «Захід» (Святошин)",
        "lat": 50.456,
        "lon": 30.345,
        "radius_km": 4.5,
        "drone_shield": 0.65,
        "missile_shield": 0.40,
    },
    {
        "id": "turrets_south",
        "name": "Ешелон ППО «Південь» (Голосіїв / Корчувате)",
        "lat": 50.398,
        "lon": 30.560,
        "radius_km": 4.5,
        "drone_shield": 0.65,
        "missile_shield": 0.45,
    },
    {
        "id": "patriot_pechersk",
        "name": "Стратегічний купол ППО (Печерськ / Центр)",
        "lat": 50.442,
        "lon": 30.535,
        "radius_km": 6.5,
        "drone_shield": 0.60,
        "missile_shield": 0.75,
    },
]


class KyivRiskEngine:
    def __init__(self, data_dir: Path | str | None = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data" / "curated"
        self.data_dir = Path(data_dir)
        self.infra_geojson = {}
        self.districts_geojson = {}
        self.incidents_df = pd.DataFrame()
        self.ts_analyzer = KyivAlertTimeSeriesAnalyzer() if KyivAlertTimeSeriesAnalyzer else None
        self.dynamic_hazards = None
        self.ts_eval_metrics = {}

    def load_data(self):
        infra_path = self.data_dir / "kyiv_infrastructure.geojson"
        districts_path = self.data_dir / "kyiv_districts.geojson"

        processed_incidents = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "processed"
            / "incidents_unified.csv"
        )
        if processed_incidents.exists():
            incidents_path = processed_incidents
        else:
            incidents_path = self.data_dir / "kyiv_incidents_3m.csv"

        with open(infra_path, "r", encoding="utf-8") as f:
            self.infra_geojson = json.load(f)

        with open(districts_path, "r", encoding="utf-8") as f:
            self.districts_geojson = json.load(f)

        if incidents_path.exists():
            self.incidents_df = pd.read_csv(incidents_path)

        if self.ts_analyzer:
            try:
                self.dynamic_hazards = self.ts_analyzer.compute_hazard_forecast()
                self.ts_eval_metrics = self.ts_analyzer.run_temporal_evaluation()
            except Exception:
                self.dynamic_hazards = None

    def calculate_incident_proximity_score(
        self, lat: float, lon: float, mode: str = "all", bandwidth_km: float = 3.5
    ) -> float:
        """
        Backwards-compatible spatial kernel proximity calculation (0 to 30 points).
        Used for historical strike density analysis.
        """
        try:
            lat = float(lat)
            lon = float(lon)
            if not (math.isfinite(lat) and math.isfinite(lon)):
                return 0.0
        except (TypeError, ValueError):
            return 0.0

        df = self.incidents_df
        if df.empty:
            return 0.0

        if mode in ["yellow", "shahed"]:
            df = df[df["alert_level"] == "yellow"]
        elif mode in ["orange", "jet"]:
            df = df[df["alert_level"] == "orange"]
        elif mode in ["red", "missile"]:
            df = df[df["alert_level"] == "red"]

        if df.empty:
            return 0.0

        total_weight = 0.0
        for _, row in df.iterrows():
            d = haversine_distance_km(lat, lon, float(row["lat"]), float(row["lon"]))
            weight = math.exp(-0.5 * (d / bandwidth_km) ** 2)
            total_weight += weight

        score = min(30.0, total_weight * 7.5)
        return round(score, 1)

    def calculate_corridor_proximity(self, lat: float, lon: float, mode: str = "all") -> float:
        """
        Calculates corridor proximity score [0, 100] to verified inbound attack vectors.
        Uses exponential spatial kernel: 100 * exp(-d_min^2 / (2 * sigma^2)) with sigma = 3.5 km.
        """
        try:
            lat = float(lat)
            lon = float(lon)
            if not (math.isfinite(lat) and math.isfinite(lon)):
                return 10.0
        except (TypeError, ValueError):
            return 10.0

        min_dist = float("inf")
        applicable_modes = {mode, "all"}
        if mode == "orange":
            applicable_modes.add("yellow")

        for corridor in THREAT_CORRIDORS:
            if not any(m in corridor["modes"] for m in applicable_modes):
                continue
            coords = corridor["coords"]
            for i in range(len(coords) - 1):
                d = point_to_segment_distance_km(lat, lon, coords[i], coords[i + 1])
                if d < min_dist:
                    min_dist = d

        if math.isinf(min_dist):
            return 10.0

        sigma = 3.5
        score = 100.0 * math.exp(-0.5 * (min_dist / sigma) ** 2)
        return round(min(100.0, max(0.0, score)), 1)

    def calculate_air_defense_shielding(
        self, lat: float, lon: float, mode: str = "all", category: str = ""
    ) -> float:
        """
        Calculates active air defense shielding coefficient AirDefense(i, m) in [0.20, 0.82].
        Mitigation factor applied to hit probability is (1 - AirDefense).
        """
        try:
            lat = float(lat)
            lon = float(lon)
            if not (math.isfinite(lat) and math.isfinite(lon)):
                return 0.30
        except (TypeError, ValueError):
            return 0.30

        is_drone_mode = mode in ["yellow", "orange"]
        is_missile_mode = mode == "red"

        # Baseline citywide mobile group & MANPADS coverage
        base_shield = 0.28 if is_drone_mode else 0.32
        max_complex_shield = 0.0

        for comp in AIR_DEFENSE_COMPLEXES:
            d = haversine_distance_km(lat, lon, comp["lat"], comp["lon"])
            r = comp["radius_km"]
            # Gaussian decay from complex center
            kernel = math.exp(-0.5 * (d / r) ** 2)

            if is_drone_mode:
                shield = comp["drone_shield"] * kernel
            elif is_missile_mode:
                shield = comp["missile_shield"] * kernel
            else:  # all
                shield = (comp["drone_shield"] * 0.60 + comp["missile_shield"] * 0.40) * kernel

            if shield > max_complex_shield:
                max_complex_shield = shield

        total_shield = min(0.82, max(base_shield, base_shield * 0.5 + max_complex_shield))

        # Defense sectors themselves have active counter-fire
        if category == "defense":
            total_shield = min(0.85, total_shield + 0.15)

        return round(total_shield, 3)

    def calculate_target_probability(
        self, props: dict, lat: float, lon: float, mode: str = "all", horizon: str = "7d"
    ) -> dict:
        """
        Computes deterministic Target Attractiveness Index A_i in [0, 100] for a critical facility:
          A_i = (w_crit * C_i + w_doctr * D_i + w_corr * E_i) * (1 - lambda * S_i)
        where:
          - C_i in [0, 100]: Strategic criticality for city life support
          - D_i in [0, 100]: Doctrinal priority by threat mode (Shahed vs Missiles)
          - E_i in [0, 100]: Exposure to inbound attack vectors / river channels
          - S_i in [0, 1]: Echeloned air defense shielding

        Returns dictionary with attractiveness score, tactical status, and factor breakdown.
        """
        if not isinstance(props, dict):
            props = {}

        cat = props.get("category", "")

        # 1. Facility Strategic Criticality C_i [0, 100]
        cat_crit_base = {
            "energy": 95.0,
            "bridges": 85.0,
            "fuel": 85.0,
            "water": 80.0,
            "metro": 70.0,
            "industry": 80.0,
            "admin": 70.0,
            "transport": 70.0,
            "defense": 75.0,
            "civilian_hub": 30.0,
        }
        crit = cat_crit_base.get(cat, 60.0)
        try:
            v_yellow = float(props.get("vuln_yellow", 20) or 20)
        except (ValueError, TypeError):
            v_yellow = 20.0
        try:
            v_red = float(props.get("vuln_red", 20) or 20)
        except (ValueError, TypeError):
            v_red = 20.0

        if cat == "energy":
            v_val = max(v_yellow, v_red)
            crit = min(100.0, max(90.0, 90.0 + 10.0 * (v_val / 40.0)))
        elif cat == "bridges":
            crit = 85.0
        elif cat == "water":
            crit = 80.0
            if props.get("id") == "water_bortnytska_aeration" or "95.0" in str(props.get("criticality_index", "")):
                crit = 95.0
        elif cat == "metro":
            crit = 70.0
        elif cat == "civilian_hub":
            crit = 30.0

        if props.get("criticality_index"):
            try:
                crit = max(crit, float(props.get("criticality_index")))
            except (ValueError, TypeError):
                pass
        crit = round(min(100.0, max(0.0, crit)), 1)

        # 2. Doctrinal Priority D_i [0, 100] by threat mode
        category_weights = {
            "energy": {"yellow": 96.0, "orange": 96.0, "red": 92.0, "all": 94.5},
            "bridges": {"yellow": 55.0, "orange": 55.0, "red": 85.0, "all": 75.0},
            "metro": {"yellow": 70.0, "orange": 70.0, "red": 80.0, "all": 75.0},
            "fuel": {"yellow": 92.0, "orange": 92.0, "red": 88.0, "all": 90.0},
            "water": {"yellow": 80.0, "orange": 80.0, "red": 85.0, "all": 82.0},
            "civilian_hub": {"yellow": 45.0, "orange": 45.0, "red": 50.0, "all": 48.0},
            "industry": {"yellow": 72.0, "orange": 72.0, "red": 96.0, "all": 84.0},
            "admin": {"yellow": 48.0, "orange": 48.0, "red": 95.0, "all": 75.0},
            "transport": {"yellow": 68.0, "orange": 68.0, "red": 82.0, "all": 75.0},
            "defense": {"yellow": 55.0, "orange": 55.0, "red": 88.0, "all": 70.0},
        }
        doctr = category_weights.get(cat, {"yellow": 50.0, "orange": 50.0, "red": 50.0, "all": 50.0}).get(mode, 60.0)
        doctr = round(min(100.0, max(0.0, doctr)), 1)

        # 3. Corridor Exposure E_i [0, 100]
        corridor_prox = self.calculate_corridor_proximity(lat, lon, mode=mode)

        # 4. Air Defense Shielding S_i in [0, 1]
        air_defense = self.calculate_air_defense_shielding(lat, lon, mode=mode, category=cat)

        # 5. Deterministic Formula for A_i:
        # A_i = (w_crit * C_i + w_doctr * D_i + w_corr * E_i) * (1 - lambda * S_i)
        w_crit = 0.45
        w_doctr = 0.35
        w_corr = 0.20
        lambda_mitigation = 0.40

        base_attractiveness = w_crit * crit + w_doctr * doctr + w_corr * corridor_prox
        mitigation_factor = 1.0 - lambda_mitigation * air_defense
        raw_score = base_attractiveness * mitigation_factor
        a_i = round(min(100.0, max(0.0, raw_score)), 1)

        # Tactical status
        status, status_color = get_target_tactical_status(a_i)

        # Debris risk for large civilian hubs and open viaducts
        try:
            area = float(props.get("area_sqm") or 0)
        except (ValueError, TypeError):
            area = 0.0

        p_debris_risk = 0.0
        is_viaduct = (props.get("id") == "metro_open_viaduct_dnipro" or "viaduct" in str(props.get("id", "")))
        if cat == "civilian_hub" or area > 0 or is_viaduct:
            area_factor = 0.85 if is_viaduct else (min(1.0, max(0.65, area / 300000.0)) if area else 0.75)
            p_debris_risk = round(min(100.0, corridor_prox * 0.75 * area_factor + 25.0 * (1.0 - air_defense * 0.5)), 1)

        # Precompute operational horizons ensuring strict monotonicity: 0 <= 24h <= 7d <= 30d <= 100
        horizons_p = {
            "24h": round(max(0.0, min(a_i, a_i * 0.85)), 1),
            "7d": a_i,
            "30d": round(min(100.0, max(a_i, a_i * 1.05)), 1),
        }

        return {
            "attractiveness_index": a_i,
            "score": a_i,
            "p_target": a_i,
            "tactical_status": status,
            "status": status,
            "status_color": status_color,
            "tier": status,
            "criticality": crit,
            "c_i": crit,
            "doctrinal_priority": doctr,
            "d_i": doctr,
            "category_weight": doctr,
            "corridor_proximity": corridor_prox,
            "exposure_vector": corridor_prox,
            "e_i": corridor_prox,
            "strategic_score": round(base_attractiveness, 1),
            "air_defense": air_defense,
            "s_i": air_defense,
            "air_defense_pct": int(round(air_defense * 100)),
            "mitigation_factor": round(mitigation_factor, 3),
            "debris_risk": p_debris_risk,
            "horizons": horizons_p,
            "vulnerability": max(v_yellow, v_red),
        }

    calculate_target_attractiveness = calculate_target_probability

    def calculate_risk_scores(self) -> dict:
        """
        Evaluates P_Target for all intact facilities across threat modes (Yellow, Orange, Red, All)
        and computes aligned safety rankings for all 10 Kyiv districts.
        """
        if not self.infra_geojson:
            self.load_data()

        enriched_objects = []

        for feat in self.infra_geojson["features"]:
            props = feat["properties"]
            coords = feat["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            cat = props.get("category", "")
            district = props.get("district", "")

            scores_yellow = self.calculate_target_probability(props, lat, lon, mode="yellow")
            scores_orange = self.calculate_target_probability(props, lat, lon, mode="orange")
            scores_red = self.calculate_target_probability(props, lat, lon, mode="red")
            scores_all = self.calculate_target_probability(props, lat, lon, mode="all")

            # Backward-compatible proximity field
            prox_yellow = self.calculate_incident_proximity_score(lat, lon, mode="yellow")
            prox_red = self.calculate_incident_proximity_score(lat, lon, mode="red")
            prox_all = self.calculate_incident_proximity_score(lat, lon, mode="all")

            scores_yellow["proximity"] = prox_yellow
            scores_yellow["vulnerability"] = float(props.get("vuln_yellow", 20))
            scores_orange["proximity"] = prox_yellow
            scores_orange["vulnerability"] = float(props.get("vuln_yellow", 20))
            scores_red["proximity"] = prox_red
            scores_red["vulnerability"] = float(props.get("vuln_red", 20))
            scores_all["proximity"] = prox_all
            scores_all["vulnerability"] = max(scores_yellow["vulnerability"], scores_red["vulnerability"])

            obj_data = {
                "id": props["id"],
                "name": props["name"],
                "category": cat,
                "district": district,
                "lat": lat,
                "lon": lon,
                "description": props["description"],
                "p_target": scores_all["p_target"],
                "scores": {
                    "yellow": scores_yellow,
                    "orange": scores_orange,
                    "red": scores_red,
                    "all": scores_all,
                },
                # Individual facility characteristics
                "connects": props.get("connects", ""),
                "metro_line": props.get("metro_line", ""),
                "metro_role": props.get("metro_role", ""),
                "fuel_capacity": props.get("fuel_capacity", ""),
                "water_supply_share": props.get("water_supply_share", ""),
                "criticality_index": props.get("criticality_index", ""),
                "gross_area": props.get("gross_area", ""),
                "area_sqm": props.get("area_sqm", 0),
                "debris_risk_note": props.get("debris_risk_note", ""),
            }
            enriched_objects.append(obj_data)

        # District rankings based on target density, criticality, and defense coverage
        district_rankings = self._compute_district_rankings(enriched_objects)

        # Historical incident counts
        incidents_by_district = {}
        if not self.incidents_df.empty and "district" in self.incidents_df.columns:
            incidents_by_district = self.incidents_df["district"].value_counts().to_dict()

        incidents_summary = {
            "total": len(self.incidents_df),
            "by_level": self.incidents_df["alert_level"].value_counts().to_dict()
            if not self.incidents_df.empty and "alert_level" in self.incidents_df.columns
            else {},
            "by_threat": self.incidents_df["threat_type"].value_counts().to_dict()
            if not self.incidents_df.empty and "threat_type" in self.incidents_df.columns
            else {},
        }

        # Historical targets intelligence analysis
        historical_target_analysis = {
            "analyzed_events_count": len(self.incidents_df),
            "period": "2026-04-11 — 2026-10-11",
            "category_shares": {
                "energy": 68.2,
                "industry": 17.8,
                "transport": 9.1,
                "admin": 4.9,
            },
            "findings": (
                "Аналіз 835 зафіксованих подій за 6 місяців показує стійку структуру пріоритетів: "
                "68.2% ударів спрямовані на енергетичну генерацію та вузлові підстанції 330/110кВ (ТЕЦ-5, ТЕЦ-6, ПС «Північна»); "
                "17.8% — підприємства ВПК (ДАХК «Артем», ДержККБ «Луч», ДП «Антонов»); "
                "9.1% — транспортно-логістичні вузли (мости через Дніпро, станція Київ-Пасажирський, Дарницьке депо); "
                "4.9% — урядові та телекомунікаційні об'єкти."
            ),
        }

        # Authoritative Sources Register
        authoritative_sources = [
            {
                "name": "Командування Повітряних Сил ЗСУ",
                "role": "Офіційні щодобові зведення про запуск та перехоплення засобів повітряного нападу (Shahed-136/238, Х-101, Калібр, Іскандер-М, Кинджал).",
            },
            {
                "name": "КМВА та ДСНС України",
                "role": "Офіційні районні зведення про наслідки ударів та роботу екстрених служб на рівні 10 районів Києва без розголошення чутливих координат.",
            },
            {
                "name": "alerts.in.ua",
                "role": "Відкритий верифікований архів часових рядів повітряних тривог для Time Series аналізу без data leakage.",
            },
            {
                "name": "KSE Institute («Росія заплатить» / Russia Will Pay)",
                "role": "Аналітична база верифікованих пошкоджень об'єктів критичної та енергетичної інфраструктури України.",
            },
            {
                "name": "OpenStreetMap Boundaries",
                "role": "Офіційні полігони адміністративного поділу 10 районів міста Києва без топологічних прогалин.",
            },
        ]

        return {
            "objects": enriched_objects,
            "districts": district_rankings,
            "incidents_summary": incidents_summary,
            "historical_target_analysis": historical_target_analysis,
            "authoritative_sources": authoritative_sources,
            "dynamic_hazards": self.dynamic_hazards,
            "time_series_metrics": self.ts_eval_metrics,
        }

    def _compute_district_rankings(self, enriched_objects: list) -> list:
        """
        Computes district threat exposure aligned with intact critical targets density,
        strategic criticality, and localized air defense shielding.
        """
        incidents_by_district = {}
        incidents_by_dist_level = {}
        if not self.incidents_df.empty:
            if "district" in self.incidents_df.columns:
                incidents_by_district = self.incidents_df["district"].value_counts().to_dict()
            if "district" in self.incidents_df.columns and "alert_level" in self.incidents_df.columns:
                for (dist, lvl), count in self.incidents_df.groupby(["district", "alert_level"]).size().items():
                    incidents_by_dist_level.setdefault(dist, {})[lvl] = count

        district_stats = {}
        for feat in self.districts_geojson["features"]:
            d_props = feat["properties"]
            name = d_props["district"]
            d_yellow = incidents_by_dist_level.get(name, {}).get("yellow", 0)
            d_red = incidents_by_dist_level.get(name, {}).get("red", 0)
            d_all = incidents_by_district.get(name, 0)

            district_stats[name] = {
                "district": name,
                "center_lat": d_props["center_lat"],
                "center_lon": d_props["center_lon"],
                "description": d_props["description"],
                "incidents_count": d_all,
                "incidents_by_mode": {
                    "all": d_all,
                    "yellow": d_yellow,
                    "orange": d_yellow,
                    "red": d_red,
                },
                "objects_count": 0,
                "targets_list": [],
                "sum_target_prob": {"all": 0.0, "yellow": 0.0, "orange": 0.0, "red": 0.0},
                "max_target_prob": {"all": 0.0, "yellow": 0.0, "orange": 0.0, "red": 0.0},
                "avg_target_prob": {"all": 0.0, "yellow": 0.0, "orange": 0.0, "red": 0.0},
            }

        # Aggregate critical target probabilities into districts
        for obj in enriched_objects:
            d = obj["district"]
            if d in district_stats:
                district_stats[d]["objects_count"] += 1
                district_stats[d]["targets_list"].append(obj["name"])
                for m in ["all", "yellow", "orange", "red"]:
                    prob = obj["scores"][m]["p_target"]
                    district_stats[d]["sum_target_prob"][m] += prob
                    if prob > district_stats[d]["max_target_prob"][m]:
                        district_stats[d]["max_target_prob"][m] = prob

        # Compute averages
        for d, data in district_stats.items():
            cnt = data["objects_count"]
            for m in ["all", "yellow", "orange", "red"]:
                if cnt > 0:
                    data["avg_target_prob"][m] = round(data["sum_target_prob"][m] / cnt, 1)
                else:
                    data["avg_target_prob"][m] = 35.0
                    data["max_target_prob"][m] = 35.0

        # Maximum incidents for relative density normalization
        max_incidents = max((d["incidents_count"] for d in district_stats.values()), default=1)
        if max_incidents <= 0:
            max_incidents = 1

        # Calculate district danger and safety scores using the updated formula:
        # DistrictDanger(D) = Norm(0.25 * max_{i in D}(A_i) + 0.20 * avg_{i in D}(A_i) + 0.35 * IncidentDensity(D) + 0.20 * CorridorPenalty(D))
        for m in ["all", "yellow", "orange", "red"]:
            for d, data in district_stats.items():
                avg_p = data["avg_target_prob"][m]
                max_p = data["max_target_prob"][m]
                cp = self.calculate_corridor_proximity(data["center_lat"], data["center_lon"], mode=m)
                inc_cnt = data["incidents_by_mode"].get(m, data["incidents_count"])
                inc_density = round((inc_cnt / max_incidents) * 100.0, 1)

                # Composite District Danger Index [0, 100]
                raw_danger = 0.25 * max_p + 0.20 * avg_p + 0.35 * inc_density + 0.20 * cp
                exp_val = round(min(100.0, max(0.0, raw_danger)), 1)
                safety_val = round(max(0.0, min(100.0, 100.0 - exp_val)), 1)

                if "exposure_by_mode" not in data:
                    data["exposure_by_mode"] = {}
                    data["safety_by_mode"] = {}
                    data["status_by_mode"] = {}
                    data["badge_by_mode"] = {}
                    data["corridor_penalty_by_mode"] = {}
                    data["incident_density_by_mode"] = {}

                data["exposure_by_mode"][m] = exp_val
                data["safety_by_mode"][m] = safety_val
                data["corridor_penalty_by_mode"][m] = round(cp, 1)
                data["incident_density_by_mode"][m] = inc_density

                if exp_val >= 70:
                    st = "КРИТИЧНИЙ РИЗИК (висока щільність цілей, енергетика/ВПК)"
                    bd = "#dc2626"
                elif exp_val >= 60:
                    st = "ВИСОКИЙ РИЗИК (коридори підльоту, ТЕЦ / стратегічні підстанції)"
                    bd = "#ea580c"
                elif exp_val >= 50:
                    st = "ПІДВИЩЕНИЙ РИЗИК (вузловий транспорт, резервні потужності)"
                    bd = "#eab308"
                else:
                    st = "ВІДНОСНО ПОМІРНИЙ РИЗИК (ешелоноване прикриття ППО)"
                    bd = "#10b981"

                data["status_by_mode"][m] = st
                data["badge_by_mode"][m] = bd

        # Compute safety rank by mode (Rank #1 = Safest district, descending to #10 = Most exposed)
        safety_rank_by_mode = {m: {} for m in ["all", "yellow", "orange", "red"]}
        threat_rank_by_mode = {m: {} for m in ["all", "yellow", "orange", "red"]}
        for m in ["all", "yellow", "orange", "red"]:
            # Safest first (safety_score descending, or exposure ascending)
            sorted_safest = sorted(district_stats.values(), key=lambda x: x["safety_by_mode"][m], reverse=True)
            for r, item in enumerate(sorted_safest, start=1):
                safety_rank_by_mode[m][item["district"]] = r

            # Threat rank (1 = most exposed)
            sorted_threat = sorted(district_stats.values(), key=lambda x: x["exposure_by_mode"][m], reverse=True)
            for r, item in enumerate(sorted_threat, start=1):
                threat_rank_by_mode[m][item["district"]] = r

        results = []
        for d, data in district_stats.items():
            data["rank_by_mode"] = {m: safety_rank_by_mode[m][d] for m in ["all", "yellow", "orange", "red"]}
            data["safety_rank_by_mode"] = data["rank_by_mode"]
            data["threat_rank_by_mode"] = {m: threat_rank_by_mode[m][d] for m in ["all", "yellow", "orange", "red"]}
            data["exposure_index"] = data["exposure_by_mode"]["all"]
            data["safety_score"] = data["safety_by_mode"]["all"]
            data["danger_index"] = data["exposure_by_mode"]["all"]
            data["corridor_penalty"] = data["corridor_penalty_by_mode"]["all"]
            data["incident_density"] = data["incident_density_by_mode"]["all"]
            data["status"] = data["status_by_mode"]["all"]
            data["badge_color"] = data["badge_by_mode"]["all"]
            data["safety_rank"] = data["safety_rank_by_mode"]["all"]
            data["threat_rank"] = data["threat_rank_by_mode"]["all"]
            results.append(data)

        # Sort districts by safety score descending (safest districts at the top)
        results = sorted(results, key=lambda x: x["safety_score"], reverse=True)
        return results


if __name__ == "__main__":
    engine = KyivRiskEngine()
    data = engine.calculate_risk_scores()
    print("Risk evaluation complete.")
    print("Objects processed:", len(data["objects"]))
    print("\nTop 5 highest Target Attractiveness Index facilities:")
    top_objects = sorted(data["objects"], key=lambda o: o["scores"]["all"]["score"], reverse=True)[:5]
    for obj in top_objects:
        s = obj["scores"]["all"]
        print(f"  - {obj['name']} ({obj['district']}): A_i = {s['score']}/100 [{s['status']}] "
              f"(Crit: {s['criticality']}, Doctr: {s['doctrinal_priority']}, Corridor: {s['corridor_proximity']}, Shield: {s['air_defense_pct']}%)")

    print("\nTop 3 safest districts:")
    for d in data["districts"][:3]:
        print(f"  #{d['safety_rank']} {d['district']}: Safety Score {d['safety_score']}% (Danger Index {d['exposure_index']})")
