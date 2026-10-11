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
        if mode == "yellow":
            df = df[df["alert_level"] == "yellow"]
        elif mode == "red":
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
        Calculates Risk Score (0-100) for Yellow, Red, and All modes for each facility.
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

            # 1. Base vulnerability
            v_yellow = float(props.get("vuln_yellow", 20))
            v_red = float(props.get("vuln_red", 20))

            # 2. Incident Proximity (0 - 30)
            prox_yellow = self.calculate_incident_proximity_score(lat, lon, mode="yellow")
            prox_red = self.calculate_incident_proximity_score(lat, lon, mode="red")
            prox_all = self.calculate_incident_proximity_score(lat, lon, mode="all")

            # 3. District density bonus (0 - 10)
            dist_incidents = incidents_by_district.get(district, 0)
            dist_factor = round((dist_incidents / max_district_incidents) * 10.0, 1)

            # 4. Temporal factor defaults (Shahed night peak bonus +15, Red peak bonus +15)
            time_factor_yellow = 16.0
            time_factor_red = 14.0

            # Combined Scores (capped at 100)
            score_yellow = min(100.0, round(v_yellow + prox_yellow + time_factor_yellow + dist_factor, 1))
            score_red = min(100.0, round(v_red + prox_red + time_factor_red + dist_factor, 1))
            score_all = min(100.0, round(max(score_yellow, score_red) * 0.7 + min(score_yellow, score_red) * 0.3, 1))

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
                "category": props["category"],
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
                "avg_red_score": 0.0,
            }

        for obj in enriched_objects:
            d = obj["district"]
            if d in district_stats:
                district_stats[d]["objects_count"] += 1
                district_stats[d]["avg_yellow_score"] += obj["scores"]["yellow"]["score"]
                district_stats[d]["avg_red_score"] += obj["scores"]["red"]["score"]

        results = []
        for d, data in district_stats.items():
            cnt = data["objects_count"]
            if cnt > 0:
                data["avg_yellow_score"] = round(data["avg_yellow_score"] / cnt, 1)
                data["avg_red_score"] = round(data["avg_red_score"] / cnt, 1)
            else:
                data["avg_yellow_score"] = 45.0
                data["avg_red_score"] = 45.0

            # Non-linear high-contrast district exposure formula
            # Base wartime threat floor: 22 pts
            # Incident exposure: up to 45 pts (scales strongly with confirmed hits/debris)
            # Facility vulnerability exposure: up to 25 pts
            inc_pts = min(45.0, data["incidents_count"] * 11.5)
            facility_pts = ((data["avg_yellow_score"] + data["avg_red_score"]) / 2.0) * 0.28
            
            # Corridor bonuses:
            corridor_bonus = 0.0
            if d in ["Оболонський", "Дарницький", "Деснянський"]:
                corridor_bonus += 8.0  # Primary drone ingress corridors
            if d in ["Шевченківський", "Солом'янський", "Печерський"]:
                corridor_bonus += 10.0 # High-density ballistic/missile target clusters

            exposure_index = round(min(96.0, 22.0 + inc_pts + facility_pts + corridor_bonus), 1)
            data["exposure_index"] = exposure_index

            # Safety score (100 - exposure) reflects residual safety margin
            data["safety_score"] = round(max(4.0, 100.0 - exposure_index), 1)

            # Strict realistic defense tiers
            if exposure_index >= 80:
                data["status"] = "КРИТИЧНА ЗАГРОЗА (висока концентрація ударів/уламків)"
                data["badge_color"] = "#dc2626"
            elif exposure_index >= 65:
                data["status"] = "ВИСОКИЙ РИЗИК (траєкторії атак, ураження інфраструктури)"
                data["badge_color"] = "#ea580c"
            elif exposure_index >= 50:
                data["status"] = "ПІДВИЩЕНИЙ РИЗИК (загроза перехоплень ППО)"
                data["badge_color"] = "#eab308"
            else:
                data["status"] = "ВІДНОСНО ПОМІРНИЙ РИЗИК (менша щільність цілей)"
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
