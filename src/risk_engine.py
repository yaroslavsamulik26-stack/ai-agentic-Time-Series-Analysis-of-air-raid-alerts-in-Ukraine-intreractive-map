"""
risk_engine.py
Geospatial Risk Scoring Engine for Kyiv Defense Analytics.

Computes multi-factor Risk Scores (0-100) for every critical infrastructure
object and safety rankings for Kyiv's 10 administrative districts.
Supports Yellow (Shahed/Drones), Red (Missiles/Ballistics), and Combined threat modes.
"""

import json
import math
from pathlib import Path
import pandas as pd


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two points in km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class KyivRiskEngine:
    def __init__(self, data_dir: Path | str | None = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data" / "curated"
        self.data_dir = Path(data_dir)
        self.infra_geojson = {}
        self.districts_geojson = {}
        self.incidents_df = pd.DataFrame()

    def load_data(self):
        infra_path = self.data_dir / "kyiv_infrastructure.geojson"
        districts_path = self.data_dir / "kyiv_districts.geojson"
        
        # Check processed unified incidents first
        processed_incidents = Path(__file__).resolve().parent.parent / "data" / "processed" / "incidents_unified.csv"
        if processed_incidents.exists():
            incidents_path = processed_incidents
        else:
            incidents_path = self.data_dir / "kyiv_incidents_3m.csv"

        with open(infra_path, "r", encoding="utf-8") as f:
            self.infra_geojson = json.load(f)

        with open(districts_path, "r", encoding="utf-8") as f:
            self.districts_geojson = json.load(f)

        self.incidents_df = pd.read_csv(incidents_path)

    def calculate_incident_proximity_score(
        self, lat: float, lon: float, mode: str = "all", bandwidth_km: float = 3.5
    ) -> float:
        """
        Calculates spatial kernel proximity (0 to 30 points) based on
        past 3-month impacts/debris falls.
        """
        df = self.incidents_df
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
            # Exponential decay
            weight = math.exp(-0.5 * (d / bandwidth_km) ** 2)
            total_weight += weight

        # Scale to max 30 points
        score = min(30.0, total_weight * 7.5)
        return round(score, 1)

    def calculate_risk_scores(self) -> dict:
        """
        Calculates Risk Score (0-100) for Yellow (Shahed), Orange (Jet Shahed),
        Red (Missiles/Ballistics), and Combined (All) modes for each facility.
        """
        if not self.infra_geojson:
            self.load_data()

        # Count incidents by district
        incidents_by_district = self.incidents_df["district"].value_counts().to_dict()
        max_district_incidents = max(incidents_by_district.values()) if incidents_by_district else 1

        enriched_objects = []

        for feat in self.infra_geojson["features"]:
            props = feat["properties"]
            coords = feat["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            district = props.get("district", "")
            cat = props.get("category", "")

            # 1. Base vulnerability
            v_yellow = float(props.get("vuln_yellow", 20))
            v_red = float(props.get("vuln_red", 20))
            v_orange = round(v_yellow * 0.6 + v_red * 0.4, 1)

            # 2. Incident Proximity (0 - 30)
            prox_yellow = self.calculate_incident_proximity_score(lat, lon, mode="yellow")
            prox_orange = self.calculate_incident_proximity_score(lat, lon, mode="orange")
            prox_red = self.calculate_incident_proximity_score(lat, lon, mode="red")
            prox_all = self.calculate_incident_proximity_score(lat, lon, mode="all")

            # 3. District density bonus (0 - 10)
            dist_incidents = incidents_by_district.get(district, 0)
            dist_factor = round((dist_incidents / max_district_incidents) * 10.0, 1)

            # 4. Temporal factor defaults
            time_factor_yellow = 16.0
            time_factor_orange = 15.0
            time_factor_red = 14.0

            # Combined Scores (capped at 100)
            score_yellow = min(100.0, round(v_yellow + prox_yellow + time_factor_yellow + dist_factor, 1))
            score_orange = min(100.0, round(v_orange + prox_orange + time_factor_orange + dist_factor, 1))
            score_red = min(100.0, round(v_red + prox_red + time_factor_red + dist_factor, 1))
            score_all = min(100.0, round(max(score_yellow, score_orange, score_red) * 0.6 + min(score_yellow, score_red) * 0.4, 1))

            # Defense facilities have active protection
            if cat == "defense":
                score_yellow = round(score_yellow * 0.65, 1)
                score_orange = round(score_orange * 0.65, 1)
                score_red = round(score_red * 0.70, 1)
                score_all = round(score_all * 0.65, 1)

            def get_tier(s: float) -> str:
                if s >= 80:
                    return "Критичний"
                if s >= 60:
                    return "Високий"
                if s >= 40:
                    return "Середній"
                return "Помірний"

            obj_data = {
                "id": props["id"],
                "name": props["name"],
                "category": cat,
                "district": district,
                "lat": lat,
                "lon": lon,
                "description": props["description"],
                "scores": {
                    "yellow": {
                        "score": score_yellow,
                        "tier": get_tier(score_yellow),
                        "vulnerability": v_yellow,
                        "proximity": prox_yellow,
                    },
                    "orange": {
                        "score": score_orange,
                        "tier": get_tier(score_orange),
                        "vulnerability": v_orange,
                        "proximity": prox_orange,
                    },
                    "red": {
                        "score": score_red,
                        "tier": get_tier(score_red),
                        "vulnerability": v_red,
                        "proximity": prox_red,
                    },
                    "all": {
                        "score": score_all,
                        "tier": get_tier(score_all),
                        "proximity": prox_all,
                    },
                },
            }
            enriched_objects.append(obj_data)

        # 5. District Safety Ranking
        district_rankings = self._compute_district_rankings(enriched_objects, incidents_by_district)

        return {
            "objects": enriched_objects,
            "districts": district_rankings,
            "incidents_summary": {
                "total": len(self.incidents_df),
                "by_level": self.incidents_df["alert_level"].value_counts().to_dict(),
                "by_threat": self.incidents_df["threat_type"].value_counts().to_dict(),
            },
        }

    def _compute_district_rankings(self, enriched_objects: list, incidents_by_district: dict) -> list:
        district_stats = {}
        for feat in self.districts_geojson["features"]:
            d_props = feat["properties"]
            name = d_props["district"]
            district_stats[name] = {
                "district": name,
                "center_lat": d_props["center_lat"],
                "center_lon": d_props["center_lon"],
                "description": d_props["description"],
                "incidents_count": incidents_by_district.get(name, 0),
                "objects_count": 0,
                "avg_yellow_score": 0.0,
                "avg_orange_score": 0.0,
                "avg_red_score": 0.0,
            }

        for obj in enriched_objects:
            d = obj["district"]
            if d in district_stats:
                district_stats[d]["objects_count"] += 1
                district_stats[d]["avg_yellow_score"] += obj["scores"]["yellow"]["score"]
                district_stats[d]["avg_orange_score"] += obj["scores"]["orange"]["score"]
                district_stats[d]["avg_red_score"] += obj["scores"]["red"]["score"]

        results = []
        for d, data in district_stats.items():
            cnt = data["objects_count"]
            if cnt > 0:
                data["avg_yellow_score"] = round(data["avg_yellow_score"] / cnt, 1)
                data["avg_orange_score"] = round(data["avg_orange_score"] / cnt, 1)
                data["avg_red_score"] = round(data["avg_red_score"] / cnt, 1)
            else:
                data["avg_yellow_score"] = 45.0
                data["avg_orange_score"] = 45.0
                data["avg_red_score"] = 45.0

            # High-contrast relative incident scaling based on actual strikes/debris
            # Prevents artificial score saturation and provides clear visual/risk contrast
            all_incident_counts = [d_info["incidents_count"] for d_info in district_stats.values()]
            min_c = min(all_incident_counts) if all_incident_counts else 0
            max_c = max(all_incident_counts) if all_incident_counts else 1

            if max_c > min_c:
                # Logarithmic normalization handles heavy-tailed strike counts
                norm_inc = (math.log(1 + data["incidents_count"]) - math.log(1 + min_c)) / (
                    math.log(1 + max_c) - math.log(1 + min_c)
                )
            else:
                norm_inc = 0.5

            # Incident intensity points: 0 to 48 pts
            inc_pts = norm_inc * 48.0

            # Strategic Infrastructure & target density bonus: up to 18 pts
            infra_weights = {
                "Солом'янський": 17.0,  # Вокзал, Жуляни, МОУ / Генштаб, хаб «Шайба», ПС «Вокзальна»
                "Голосіївський": 17.5,   # ТЕЦ-5, ПС «Новокиївська», нафтобаза Корчувате, Kärcher, ППО «Південь»
                "Оболонський": 17.0,     # Київська ГЕС, Північний міст, ПС «Оболонь», ПММ Богатирська, човнова база, ППО «Північ»
                "Дарницький": 15.5,      # ПС «Позняки», Дарницький вокзал, нафтохаб Бортничі, Південний міст
                "Шевченківський": 16.5,  # ДАХК «Артем», ДержККБ «Луч», Охматдит, Телевежа, «Київстар», Довженка, КМДА
                "Подільський": 12.5,     # ПС «Північна», Куренівська промзона, «Фармак», Виноградар
                "Святошинський": 13.0,   # ДП «Антонов» (Святошинський авіакомплекс), ППО «Захід»
                "Деснянський": 9.5,      # ТЕЦ-6, Деснянська водопровідна станція
                "Дніпровський": 8.5,     # Дарницька ТЕЦ, депо «Дарниця», Комфорт Таун, мости
                "Печерський": 7.5,       # Урядовий квартал, Військовий госпіталь (ешелон Patriot/ППО)
            }
            infra_pts = infra_weights.get(d, 8.0)

            # Base wartime threat floor: 25.0 pts (any district in Kyiv has background risk during air alarms)
            raw_exposure = 25.0 + inc_pts + infra_pts
            exposure_index = round(min(95.0, max(20.0, raw_exposure)), 1)
            data["exposure_index"] = exposure_index

            # Safety score (100 - exposure) reflects residual safety margin
            data["safety_score"] = round(max(5.0, 100.0 - exposure_index), 1)

            # Strict realistic defense tiers with distinctive visual separation
            if exposure_index >= 75:
                data["status"] = "КРИТИЧНИЙ РИЗИК (масовані удари, пріоритетні оборонні цілі)"
                data["badge_color"] = "#dc2626"
            elif exposure_index >= 60:
                data["status"] = "ВИСОКИЙ РИЗИК (коридори дронів, ТЕЦ / стратегічні підстанції)"
                data["badge_color"] = "#ea580c"
            elif exposure_index >= 45:
                data["status"] = "ПІДВИЩЕНИЙ РИЗИК (падіння уламків збиттів, вузловий транспорт)"
                data["badge_color"] = "#eab308"
            else:
                data["status"] = "ВІДНОСНО ПОМІРНИЙ РИЗИК (мінімальна кількість влучань/уламків)"
                data["badge_color"] = "#10b981"

            results.append(data)

        # Sort districts by exposure descending (most exposed first)
        results = sorted(results, key=lambda x: x["exposure_index"], reverse=True)
        for rank, item in enumerate(results, start=1):
            item["threat_rank"] = rank

        return results


if __name__ == "__main__":
    engine = KyivRiskEngine()
    data = engine.calculate_risk_scores()
    print("Risk evaluation complete.")
    print("Objects processed:", len(data["objects"]))
    print("\nTop 3 highest threat districts:")
    for d in data["districts"][:3]:
        print(f"#{d['threat_rank']} {d['district']}: Exposure Index {d['exposure_index']}, Incidents: {d['incidents_count']}")
