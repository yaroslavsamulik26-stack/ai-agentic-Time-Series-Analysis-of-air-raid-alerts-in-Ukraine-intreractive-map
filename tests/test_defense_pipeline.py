import unittest
import json
from pathlib import Path
import pandas as pd
import numpy as np

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser import KyivDataIngestionPipeline
from src.risk_engine import KyivRiskEngine, haversine_distance_km
from src.time_series import KyivAlertTimeSeriesAnalyzer


class TestKyivDefensePipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.project_root = PROJECT_ROOT
        cls.incidents_path = cls.project_root / "data" / "processed" / "incidents_unified.csv"
        cls.alerts_path = cls.project_root / "data" / "processed" / "alerts_unified.csv"
        cls.infra_path = cls.project_root / "data" / "curated" / "kyiv_infrastructure.geojson"
        cls.districts_path = cls.project_root / "data" / "curated" / "kyiv_districts.geojson"
        cls.index_path = cls.project_root / "index.html"
        cls.parser = KyivDataIngestionPipeline(cls.project_root)

    # --- 1. Parser & Text Normalization Tests ---
    def test_apostrophe_normalization(self):
        """Test Ukrainian typographical apostrophes (U+2019, U+02BC) normalization."""
        texts = [
            "Вибухи в Солом’янському районі",
            "Вибухи в Соломʼянському районі",
            "Вибухи в Солом'янському районі"
        ]
        for t in texts:
            districts = self.parser.extract_districts(t)
            self.assertIn("Солом'янський", districts, f"Failed to match district for text: {t}")

    def test_multi_district_extraction(self):
        """Test extraction of multiple districts in single report."""
        sample_text = "Падіння уламків зафіксовано в Оболонському та Дарницькому районах."
        districts = self.parser.extract_districts(sample_text)
        self.assertIn("Оболонський", districts)
        self.assertIn("Дарницький", districts)

    def test_threat_type_classification(self):
        """Test classification of drone_jet, drone_shahed, missile_ballistic, missile_cruise."""
        # Jet drone (unified with drone_shahed per tactical directive)
        t_jet, lvl_jet = self.parser.classify_threat("Атака реактивного шахеда Shahed-238 на міст")
        self.assertEqual(t_jet, "drone_shahed")
        self.assertEqual(lvl_jet, "yellow")

        # Piston drone
        t_shahed, lvl_shahed = self.parser.classify_threat("Рух групи ударних БпЛА шахед з півночі")
        self.assertEqual(t_shahed, "drone_shahed")
        self.assertEqual(lvl_shahed, "yellow")

        # Ballistic missile
        t_bal, lvl_bal = self.parser.classify_threat("Швидкісна балістика на Київ, Іскандер-М укриття!")
        self.assertEqual(t_bal, "missile_ballistic")
        self.assertEqual(lvl_bal, "red")

        # Cruise missile
        t_cr, lvl_cr = self.parser.classify_threat("Крилата ракета Х-101 курсом на правий берег")
        self.assertEqual(t_cr, "missile_cruise")
        self.assertEqual(lvl_cr, "red")

        # Generic missile and debris report (must be RED, not misclassified as Shahed)
        t_gen, lvl_gen = self.parser.classify_threat("У Подільському районі влучання ракети у складські приміщення")
        self.assertEqual(t_gen, "missile_cruise")
        self.assertEqual(lvl_gen, "red")

        t_deb, lvl_deb = self.parser.classify_threat("Падіння уламків ракети у Дарницькому районі")
        self.assertEqual(t_deb, "missile_cruise")
        self.assertEqual(lvl_deb, "red")

        # Shahed-238 (Jet) unified with drone_shahed
        t_s238, lvl_s238 = self.parser.classify_threat("Зафіксовано рух швидкісного Shahed-238")
        self.assertEqual(t_s238, "drone_shahed")
        self.assertEqual(lvl_s238, "yellow")

        # Kinzhal / Ballistic variants
        t_kz, lvl_kz = self.parser.classify_threat("Пуск кинжал по урядовому кварталу")
        self.assertEqual(t_kz, "missile_ballistic")
        self.assertEqual(lvl_kz, "red")

        # Decoy / Gerber / Parus
        t_dec, lvl_dec = self.parser.classify_threat("Атака дрона-приманки Гербера без бойової частини")
        self.assertEqual(t_dec, "drone_decoy")
        self.assertEqual(lvl_dec, "yellow")

    def test_dniprovskyi_and_desnyanskyi_filtering(self):
        """Verify Dniprovskyi and Desnyanskyi districts are correctly extracted and not false-filtered."""
        d_dnipro = self.parser.extract_districts("У Дніпровському районі падіння уламків на прибудинкову територію")
        self.assertIn("Дніпровський", d_dnipro)

        d_desna = self.parser.extract_districts("У Деснянському районі зафіксовано пожежу покрівлі")
        self.assertIn("Деснянський", d_desna)

    def test_processed_incidents_dataset(self):
        """Verify processed incidents CSV schema, non-emptiness, and coordinates."""
        self.assertTrue(cls_file_exists := self.incidents_path.exists(), "incidents_unified.csv does not exist")
        df = pd.read_csv(self.incidents_path)
        self.assertGreaterEqual(len(df), 700, "Dataset should have at least 700 verified incidents")

        required_cols = {"id", "datetime", "district", "lat", "lon", "alert_level", "threat_type"}
        for col in required_cols:
            self.assertIn(col, df.columns)

        # Coordinate boundaries (Kyiv metro area)
        self.assertTrue((df["lat"] >= 50.1).all() and (df["lat"] <= 50.7).all(), "Latitude out of Kyiv bounds")
        self.assertTrue((df["lon"] >= 30.0).all() and (df["lon"] <= 31.0).all(), "Longitude out of Kyiv bounds")

        # Alert level distribution check (Unified Shahed = yellow, Missiles = red)
        alert_levels = set(df["alert_level"].unique())
        self.assertIn("yellow", alert_levels)
        self.assertIn("red", alert_levels)

        # Unified Shahed verification: all drone variants unified into drone_shahed
        threat_types = set(df["threat_type"].unique())
        self.assertNotIn("drone_jet", threat_types, "drone_jet must be unified into drone_shahed")
        self.assertNotIn("drone_decoy", threat_types, "drone_decoy must be unified into drone_shahed")
        self.assertIn("drone_shahed", threat_types)

        # 6-month period check: April 11 to October 11, 2026
        min_date = df["datetime"].min()
        max_date = df["datetime"].max()
        self.assertTrue(min_date.startswith("2026-04-11"), f"Expected start date 2026-04-11, got {min_date}")
        self.assertTrue(max_date.startswith("2026-10-11"), f"Expected end date 2026-10-11, got {max_date}")

        # Verified significant missile presence
        red_count = (df["alert_level"] == "red").sum()
        self.assertGreaterEqual(red_count, 50, f"Expected at least 50 missile/ballistic strikes, got {red_count}")

    def test_processed_alerts_dataset(self):
        """Verify processed alerts unified CSV schema, 6-month period, and non-emptiness (R1)."""
        self.assertTrue(self.alerts_path.exists(), "alerts_unified.csv does not exist")
        df = pd.read_csv(self.alerts_path)
        self.assertGreaterEqual(len(df), 150, "Dataset should have at least 150 alert records")

        required_cols = {"alert_id", "started_at", "finished_at", "duration_minutes", "threat_type", "alert_level", "region"}
        for col in required_cols:
            self.assertIn(col, df.columns)

        min_date = df["started_at"].min()
        max_date = df["finished_at"].max()
        self.assertTrue(min_date.startswith("2026-04-11"), f"Expected start date 2026-04-11, got {min_date}")
        self.assertTrue(max_date.startswith("2026-10-11"), f"Expected end date 2026-10-11, got {max_date}")

        alert_levels = set(df["alert_level"].unique())
        self.assertIn("yellow", alert_levels)
        self.assertIn("red", alert_levels)

    # --- 2. Risk Engine & Infrastructure Tests ---
    def test_infrastructure_curated_data(self):
        """Test infrastructure catalog completeness (>= 60 objects), all categories presence."""
        self.assertTrue(self.infra_path.exists(), "kyiv_infrastructure.geojson missing")
        with open(self.infra_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        self.assertGreaterEqual(len(features), 60, "Expected at least 60 verified infrastructure objects")

        categories = set(f["properties"]["category"] for f in features)
        expected_categories = {
            "defense", "energy", "transport", "admin", "industry",
            "bridges", "metro", "fuel", "water", "civilian_hub"
        }
        for cat in expected_categories:
            self.assertIn(cat, categories, f"Category {cat} missing from features")

        # Ensure defense objects exist and have proper coverage
        defense_objects = [f for f in features if f["properties"]["category"] == "defense"]
        self.assertGreaterEqual(len(defense_objects), 3, "Expected at least 3 air defense sectors/turret lines")

    def test_bridges_infrastructure(self):
        """Verify strategic bridges across Dnipro: count, C=85.0 priority, and inter-bank connectivity."""
        engine = KyivRiskEngine()
        results = engine.calculate_risk_scores()
        objects = {o["id"]: o for o in results["objects"]}

        expected_bridge_ids = [
            "bridge_north", "bridge_south", "bridge_metro", "bridge_paton",
            "bridge_darnytskyi", "bridge_podilskyi", "bridge_rusanivskyi",
            "bridge_havanskyi", "overpass_shuliavskyi"
        ]
        for b_id in expected_bridge_ids:
            self.assertIn(b_id, objects, f"Bridge {b_id} missing from catalog")
            bridge = objects[b_id]
            self.assertEqual(bridge["category"], "bridges")
            self.assertTrue(bool(bridge.get("connects")), f"Bridge {b_id} missing connects property")
            # Verify high cruise missile priority C = 85.0
            self.assertEqual(bridge["scores"]["red"]["category_weight"], 85.0)
            self.assertGreaterEqual(bridge["scores"]["red"]["criticality"], 80.0)

    def test_metro_infrastructure(self):
        """Verify Kyiv Metro critical nodes: depots TCh-1, TCh-2, TCh-3, substations, and open viaduct."""
        engine = KyivRiskEngine()
        results = engine.calculate_risk_scores()
        objects = {o["id"]: o for o in results["objects"]}

        expected_metro_ids = [
            "metro_depot_darnytsia", "metro_depot_obolon", "metro_depot_kharkivske",
            "metro_tpp_khreshchatyk", "metro_tpp_pochayna", "metro_tpp_livoberezhna",
            "metro_tpp_lybidska", "metro_tpp_lukianivska", "metro_open_viaduct_dnipro"
        ]
        for m_id in expected_metro_ids:
            self.assertIn(m_id, objects, f"Metro object {m_id} missing from catalog")
            metro_obj = objects[m_id]
            self.assertEqual(metro_obj["category"], "metro")
            self.assertIn("metro_line", metro_obj)
            self.assertIn("metro_role", metro_obj)
            self.assertGreaterEqual(metro_obj["scores"]["all"]["p_target"], 10.0)

        viaduct = objects["metro_open_viaduct_dnipro"]
        self.assertGreater(viaduct["scores"]["all"].get("debris_risk", 0), 0.0)
        self.assertTrue(bool(viaduct.get("debris_risk_note")))

    def test_fuel_water_civilian_infrastructure(self):
        """Verify fuel depots, water utility (Bortnytska R_i=95.0), and civilian mega-hubs (>100k sqm, debris risk)."""
        engine = KyivRiskEngine()
        results = engine.calculate_risk_scores()
        objects = {o["id"]: o for o in results["objects"]}

        # Fuel depots
        fuel_ids = ["fuel_depot_sviatoshyn", "fuel_terminal_darnytsia", "fuel_depot_korchuvate"]
        for f_id in fuel_ids:
            self.assertIn(f_id, objects)
            self.assertEqual(objects[f_id]["category"], "fuel")

        # Water utility
        water_ids = ["water_desnianska_station", "water_dniprovska_station", "water_bortnytska_aeration"]
        for w_id in water_ids:
            self.assertIn(w_id, objects)
            self.assertEqual(objects[w_id]["category"], "water")

        bortnytska = objects["water_bortnytska_aeration"]
        self.assertGreaterEqual(bortnytska["scores"]["red"]["criticality"], 95.0)

        # Civilian mega-hubs (> 100 000 m²)
        mall_ids = [
            "hub_mall_retroville", "hub_mall_respublika", "hub_mall_blockbuster",
            "hub_mall_lavina", "hub_mall_ocean_plaza", "hub_mall_river_mall"
        ]
        for m_id in mall_ids:
            self.assertIn(m_id, objects)
            mall = objects[m_id]
            self.assertEqual(mall["category"], "civilian_hub")
            self.assertGreaterEqual(mall.get("area_sqm", 0), 100_000)
            self.assertGreater(mall["scores"]["all"].get("debris_risk", 0), 0.0)

    def test_risk_engine_calculations(self):
        """Test risk engine output: district rankings, scores, and mitigation."""
        engine = KyivRiskEngine()
        results = engine.calculate_risk_scores()

        self.assertIn("districts", results)
        self.assertIn("objects", results)
        self.assertEqual(len(results["districts"]), 10, "Expected 10 Kyiv districts")
        self.assertGreaterEqual(len(results["objects"]), 60, "Expected at least 60 evaluated objects")

        for d in results["districts"]:
            self.assertGreaterEqual(d["exposure_index"], 0.0)
            self.assertLessEqual(d["exposure_index"], 100.0)
            self.assertAlmostEqual(d["exposure_index"] + d["safety_score"], 100.0, places=1)

            # Verify mode-specific exposure indices exist
            self.assertIn("exposure_by_mode", d)
            self.assertIn("rank_by_mode", d)
            for m in ["all", "yellow", "orange", "red"]:
                self.assertIn(m, d["exposure_by_mode"])
                self.assertGreaterEqual(d["exposure_by_mode"][m], 0.0)
                self.assertLessEqual(d["exposure_by_mode"][m], 100.0)
                self.assertIn(m, d["rank_by_mode"])

        # Verify threat mode scores and P_Target for objects
        for obj in results["objects"]:
            scores = obj["scores"]
            for mode in ["yellow", "orange", "red", "all"]:
                self.assertIn(mode, scores)
                self.assertGreaterEqual(scores[mode]["score"], 0.0)
                self.assertLessEqual(scores[mode]["score"], 100.0)
                self.assertIn("p_target", scores[mode])
                self.assertGreaterEqual(scores[mode]["p_target"], 0.0)
                self.assertLessEqual(scores[mode]["p_target"], 100.0)
                self.assertIn("category_weight", scores[mode])
                self.assertIn("corridor_proximity", scores[mode])
                self.assertIn("air_defense", scores[mode])
                self.assertIn("vulnerability", scores[mode])
                self.assertGreaterEqual(scores[mode]["vulnerability"], 10.0)

                # Verify exact precalculated horizons
                self.assertIn("horizons", scores[mode])
                for h_key in ["24h", "7d", "30d"]:
                    self.assertIn(h_key, scores[mode]["horizons"])
                    self.assertGreaterEqual(scores[mode]["horizons"][h_key], 0.0)
                    self.assertLessEqual(scores[mode]["horizons"][h_key], 100.0)
                self.assertLessEqual(scores[mode]["horizons"]["24h"], scores[mode]["horizons"]["30d"])

        # Verify dynamic calibrated district spectrum spanning tiers
        all_exposures = [d["exposure_index"] for d in results["districts"]]
        self.assertTrue(any(exp >= 60.0 for exp in all_exposures), "High risk tier (>=60) must be populated")
        self.assertTrue(any(exp <= 45.0 for exp in all_exposures), "Moderate risk tier (<=45) must be populated")

        self.assertIn("authoritative_sources", results)
        self.assertIn("historical_target_analysis", results)

    def test_haversine_distance(self):
        """Verify spatial kernel distance function."""
        # Distance between Kyiv Independence Square (50.4501, 30.5234) and Kyiv TV Tower (50.4714, 30.4533) ~5.4 km
        d = haversine_distance_km(50.4501, 30.5234, 50.4714, 30.4533)
        self.assertAlmostEqual(d, 5.4, delta=0.5)

    # --- 3. Time Series Analytics Tests ---
    def test_time_series_leak_free_evaluation(self):
        """Verify time series evaluation runs without look-ahead leakage."""
        analyzer = KyivAlertTimeSeriesAnalyzer()
        eval_metrics = analyzer.run_temporal_evaluation()

        self.assertIn("metrics", eval_metrics)
        metrics = eval_metrics["metrics"]
        self.assertIn("model_roc_auc", metrics)
        self.assertIn("baseline_roc_auc", metrics)
        self.assertIn("model_brier_score", metrics)

        # 6-month period temporal validation: Train April-August, Test September-October
        self.assertIn("2026-04-11", eval_metrics["train_period"])
        self.assertIn("2026-08-31", eval_metrics["train_period"])
        self.assertIn("2026-09-01", eval_metrics["test_period"])
        self.assertIn("2026-10-11", eval_metrics["test_period"])

        # Probabilistic validation
        self.assertGreaterEqual(metrics["model_roc_auc"], 0.5)
        self.assertLessEqual(metrics["model_roc_auc"], 1.0)
        self.assertGreaterEqual(metrics["model_brier_score"], 0.0)
        self.assertLessEqual(metrics["model_brier_score"], 0.5)

    # --- 4. Dashboard & Artifact Integrity Tests ---
    def test_index_html_integrity(self):
        """Verify generated dashboard exists, has size > 500KB, and contains key components."""
        self.assertTrue(self.index_path.exists(), "index.html missing")
        content = self.index_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 500_000, "Dashboard file is unexpectedly small")

        # Check required architectural features
        self.assertIn("NotebookLM Defense Intel Briefing", content)
        self.assertIn("THREAT_CORRIDORS", content)
        self.assertIn("corridorsLayerGroup", content)
        self.assertIn("fa-shield-halved", content)
        self.assertIn("Google Maps", content)
        self.assertIn("Google Satellite", content)
        self.assertIn("Ударні БпЛА (Shahed)", content)
        self.assertIn("Всі загрози", content)
        self.assertIn("Ешелони ППО & Турелі", content)
        self.assertIn("NOTEBOOKLM_DIGEST", content)
        self.assertIn("copyNotebookLMDigest", content)
        self.assertIn("corridor-flow", content)
        self.assertIn("modal-nblm-missiles", content)
        self.assertIn("modal-nblm-shahed", content)

        # Verify elimination of incident pin layers completely from map
        self.assertNotIn("incidentsLayerGroup", content, "incidentsLayerGroup must be completely removed")
        self.assertIn("tab-priority-targets", content, "Priority targets tab must be present")
        self.assertIn("Пріоритетні цілі & Прогноз", content, "Priority targets label must be present")
        self.assertIn("P_Target", content)

        # Authoritative data sources formalization in UI
        self.assertIn("alerts.in.ua", content)
        self.assertIn("КМВА", content)
        self.assertIn("ДСНС", content)
        self.assertIn("Russia Will Pay", content)

        # Acceptance Criteria: Top panel category filter chips presence
        self.assertIn("topCategoryFilters", content)
        self.assertIn('data-cat="bridges"', content)
        self.assertIn('data-cat="metro"', content)
        self.assertIn('data-cat="fuel"', content)
        self.assertIn('data-cat="water"', content)
        self.assertIn('data-cat="civilian_hub"', content)
        self.assertIn('data-cat="transport"', content)

        # Responsive styling for mobile viewports (<768px, <480px, <360px)
        self.assertIn("@media (max-width: 768px)", content)
        self.assertIn("@media (max-width: 480px)", content)
        self.assertIn("@media (max-width: 360px)", content)
        self.assertIn("getDistrictStatusInfo", content)

        # Ensure obsolete Dark Map tile is completely absent
        self.assertNotIn("cartocdn", content.lower(), "CartoDB / Dark map tiles should be eliminated")

    def test_ui_terminology_localization(self):
        """Verify that UI contains 3 threat modes, Ukrainian terminology, structured popups, and no technical English identifiers."""
        content = self.index_path.read_text(encoding="utf-8")

        # Threat mode switcher: 3 clear options (R2)
        self.assertIn("Всі загрози", content)
        self.assertIn("Ударні БпЛА (Shahed)", content)
        self.assertIn("Ракети (Крилаті / Балістика)", content)

        # Ukrainian terminology localization (R3)
        self.assertIn("Жовтий рівень (БпЛА)", content)
        self.assertIn("Червоний рівень (Ракети)", content)
        self.assertIn("Падіння уламків", content)
        self.assertIn("Пряме влучання", content)
        self.assertIn("Збиття в повітрі", content)
        self.assertIn("Балістична ракета", content)
        self.assertIn("Крилата ракета", content)

        # Structured concise popup fields for critical target facilities
        self.assertIn("<b>Район:</b>", content)
        self.assertIn("<b>Категорія:</b>", content)
        self.assertIn("<b>Ймовірність ураження:</b>", content)
        self.assertIn("<b>Пріоритетність цілі:</b>", content)
        self.assertIn("<b>Захист ППО:</b>", content)
        self.assertIn("<b>Опис об'єкта:</b>", content)

        # Ensure no repetitive location strings like "Дарницький, Дарницький"
        self.assertNotIn("Дарницький, Дарницький", content)
        self.assertNotIn("Оболонський, Оболонський", content)
        self.assertNotIn("Святошинський, Святошинський", content)

        # Technical identifiers should not be displayed in UI badges/labels/popups
        forbidden_ui_patterns = [
            "<b>drone_shahed</b>",
            "<b>drone_jet</b>",
            "<b>drone_decoy</b>",
            "<b>missile_ballistic</b>",
            "<b>missile_cruise</b>",
            "<b>debris_fall</b>",
            "<b>direct_hit</b>",
            "<b>intercepted_airburst</b>",
        ]
        for pattern in forbidden_ui_patterns:
            self.assertNotIn(pattern, content)

        # Localized methodology terms and 6-month holdout metrics in modal
        self.assertIn("Навчальна вибірка (Train)", content)
        self.assertIn("Тестова вибірка (Test)", content)
        self.assertIn('id="metric-alerts-cnt">169<', content)
        self.assertIn('id="metric-roc-auc">0.651<', content)
        self.assertIn('id="modal-nblm-total">835<', content)
        self.assertIn('id="modal-nblm-shahed">746<', content)
        self.assertIn('id="modal-nblm-missiles">89<', content)
        self.assertIn('id="modal-nblm-turrets">3 сектори<', content)
        self.assertNotIn("Оболонський район, Оболонь,", content)

    def test_index_html_no_js_syntax_quote_errors(self):
        """Verify index.html contains no unescaped single quotes breaking JS string literals."""
        content = self.index_path.read_text(encoding="utf-8")
        import re
        scripts = re.findall(r'<script.*?>([\s\S]*?)</script>', content, re.IGNORECASE)
        for s in scripts:
            for line in s.split('\n'):
                trimmed = line.strip()
                if trimmed.startswith("container.innerHTML = '") and trimmed.endswith("';"):
                    inner = trimmed[len("container.innerHTML = '"):-2]
                    self.assertNotIn("'", inner, f"Broken unescaped single quote found in: {line}")


if __name__ == "__main__":
    unittest.main()

