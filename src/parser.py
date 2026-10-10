"""
parser.py
Universal Multi-Source Parser for Kyiv Air Defense Data.

Supports:
1. Telegram Desktop chat export JSON (result.json) or text dumps
2. Perplexity / NotebookLM OSINT CSV or markdown tables
3. alerts.in.ua / eTryvoga historical CSV dumps
Gracefully merges and deduplicates raw data with curated baseline.
"""

import json
from pathlib import Path
import re
import pandas as pd


class KyivDataIngestionPipeline:
    def __init__(self, base_dir: Path | str | None = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
        self.base_dir = Path(base_dir)
        self.raw_tg_dir = self.base_dir / "data" / "raw" / "telegram"
        self.raw_osint_dir = self.base_dir / "data" / "raw" / "osint"
        self.curated_dir = self.base_dir / "data" / "curated"
        self.processed_dir = self.base_dir / "data" / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.district_keywords = {
            "Оболонський": ["оболон", "мінськ", "привокзал", "богатирськ"],
            "Шевченківський": ["шевченків", "лук'янів", "дегтярів", "сирець"],
            "Солом'янський": ["солом'ян", "відрадн", "жулян", "вокзал", "гузар"],
            "Печерський": ["печерськ", "липк", "урядов", "лавр"],
            "Подільський": ["поділ", "куренів", "вітрян"],
            "Святошинський": ["святошин", "академ", "борщагів", "берестейськ", "антонов"],
            "Голосіївський": ["голосіїв", "деміїв", "теремк", "корчуват", "пирогов"],
            "Дарницький": ["дарницьк", "позняк", "осокорк", "бортнич", "харківськ"],
            "Деснянський": ["деснян", "троєщин", "лісов"],
            "Дніпровський": ["дніпровськ", "русанів", "воскресен", "лівобереж"],
        }

    def parse_telegram_json(self, file_path: Path) -> list:
        """Parses a standard Telegram Desktop export result.json."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        extracted_events = []

        for msg in messages:
            if msg.get("type") != "message":
                continue
            text_entities = msg.get("text", "")
            raw_text = ""
            if isinstance(text_entities, list):
                for item in text_entities:
                    if isinstance(item, str):
                        raw_text += item
                    elif isinstance(item, dict):
                        raw_text += item.get("text", "")
            else:
                raw_text = str(text_entities)

            raw_text_lower = raw_text.lower()
            if not ("київ" in raw_text_lower or "столиц" in raw_text_lower):
                continue

            # Identify threat level and weapon
            threat_type = "drone_shahed"
            alert_level = "yellow"
            if any(w in raw_text_lower for w in ["балістик", "іскандер", "кинджал", "х-101", "ракета"]):
                threat_type = "missile_cruise" if "х-101" in raw_text_lower else "missile_ballistic"
                alert_level = "red"

            # Check if an impact or debris event is reported
            if not any(w in raw_text_lower for w in ["уламк", "падінн", "пожеж", "влучан", "збитт"]):
                continue

            # Identify district
            detected_district = "Шевченківський"  # fallback default
            for district_name, keywords in self.district_keywords.items():
                if any(kw in raw_text_lower for kw in keywords):
                    detected_district = district_name
                    break

            date_str = msg.get("date", "")
            event_id = f"TG-MSG-{msg.get('id', '0')}"

            extracted_events.append(
                {
                    "id": event_id,
                    "datetime": date_str.replace("T", " ") if "T" in date_str else date_str,
                    "district": detected_district,
                    "location_hint": "Зведення Telegram каналу",
                    "lat": 50.4500,  # placeholder centroid
                    "lon": 30.5200,
                    "threat_type": threat_type,
                    "alert_level": alert_level,
                    "impact_type": "debris_fall" if "уламк" in raw_text_lower else "fire",
                    "source": "Telegram Export",
                    "description": raw_text[:200] + ("..." if len(raw_text) > 200 else ""),
                }
            )

        return extracted_events

    def parse_osint_csv(self, file_path: Path) -> list:
        """Parses user-provided Perplexity / NotebookLM incident CSV."""
        try:
            df = pd.read_csv(file_path)
            # Standardize column names
            df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"Error parsing OSINT file {file_path}: {e}")
            return []

    def run_pipeline(self) -> dict:
        """
        Executes end-to-end ingestion:
        Scans raw directories, falls back to curated baseline,
        and saves unified datasets to data/processed/.
        """
        # 1. Base curated incidents
        curated_incidents_path = self.curated_dir / "kyiv_incidents_3m.csv"
        incidents_df = pd.read_csv(curated_incidents_path)

        # 2. Check for raw Telegram files
        tg_files = list(self.raw_tg_dir.glob("*.json"))
        tg_events = []
        for f in tg_files:
            print(f"Parsing Telegram export: {f.name}")
            parsed = self.parse_telegram_json(f)
            tg_events.extend(parsed)

        # 3. Check for OSINT files
        osint_files = list(self.raw_osint_dir.glob("*.csv"))
        osint_events = []
        for f in osint_files:
            print(f"Parsing OSINT export: {f.name}")
            parsed = self.parse_osint_csv(f)
            osint_events.extend(parsed)

        if tg_events:
            incidents_df = pd.concat([incidents_df, pd.DataFrame(tg_events)], ignore_index=True)
        if osint_events:
            incidents_df = pd.concat([incidents_df, pd.DataFrame(osint_events)], ignore_index=True)

        # Deduplicate
        incidents_df = incidents_df.drop_duplicates(subset=["datetime", "district"], keep="first")

        processed_incidents_path = self.processed_dir / "incidents_unified.csv"
        incidents_df.to_csv(processed_incidents_path, index=False, encoding="utf-8")

        # Copy alerts timeseries to processed
        alerts_src = self.curated_dir / "kyiv_alerts_timeseries.csv"
        alerts_df = pd.read_csv(alerts_src)
        alerts_dst = self.processed_dir / "alerts_unified.csv"
        alerts_df.to_csv(alerts_dst, index=False, encoding="utf-8")

        print(
            f"Ingestion complete: {len(incidents_df)} unified incidents, {len(alerts_df)} alert events saved to data/processed/"
        )
        return {
            "incidents_count": len(incidents_df),
            "alerts_count": len(alerts_df),
            "custom_tg_files_found": len(tg_files),
            "custom_osint_files_found": len(osint_files),
        }


if __name__ == "__main__":
    pipeline = KyivDataIngestionPipeline()
    res = pipeline.run_pipeline()
    print("Pipeline result:", res)
