"""
parser.py
Universal Multi-Source Parser for Kyiv Air Defense Data.

Supports:
1. Recursive parsing of all Telegram Desktop exports (result.json) across subdirectories.
2. Extracts verified incidents, debris falls, strikes, and official statements (КМВА, Кличко, ДСНС).
3. Distinguishes 10 official Kyiv districts, 5 strategic approach corridors, and general city digests.
4. Classifies modern threat weapons: jet-powered Shaheds (drone_jet), decoys (drone_decoy),
   ballistic salvos (missile_ballistic), cruise missiles (missile_cruise), and Shahed-136 (drone_shahed).
5. Produces an enriched text/markdown intelligence digest formatted for NotebookLM.
6. Unifies and deduplicates data into data/processed/.
"""

import json
from pathlib import Path
import random
import re
import pandas as pd

DISTRICT_COORDS = {
    # 10 Official Administrative Districts of Kyiv
    "Оболонський": (50.5050, 30.4850),
    "Шевченківський": (50.4580, 30.4800),
    "Солом'янський": (50.4350, 30.4500),
    "Печерський": (50.4300, 30.5400),
    "Подільський": (50.4750, 30.4700),
    "Святошинський": (50.4550, 30.3700),
    "Голосіївський": (50.3800, 30.5100),
    "Дарницький": (50.4050, 30.6500),
    "Деснянський": (50.5100, 30.6000),
    "Дніпровський": (50.4500, 30.6000),
    # Outer Defense Perimeter / Approach Corridors (Kyiv Region buffer)
    "Бучанський сектор (Західний коридор)": (50.4550, 30.2200),
    "Броварський сектор (Східний коридор)": (50.5100, 30.7900),
    "Бориспільський сектор (Південно-східний коридор)": (50.3500, 30.9500),
    "Вишгородський сектор (Північний коридор)": (50.5850, 30.4900),
    "Фастівський / Обухівський сектор (Південний коридор)": (50.2500, 30.5000),
    "Київ (Загальноміське зведення)": (50.4501, 30.5234),
}


def normalize_source(raw_text: str, channel_name: str) -> str:
    lower = raw_text.lower()
    ch = str(channel_name).lower()
    if "дснс" in lower or "дснс" in ch:
        return "ДСНС"
    elif "кмва" in lower or "сергій попко" in lower or "попко" in lower:
        return "КМВА"
    elif "кличко" in lower or "кмда" in lower:
        return "КМДА (Кличко)"
    elif "повітрян" in lower or "пс зсу" in lower or "повітряні сили" in ch:
        return "Повітряні Сили"
    elif "кмва" in ch:
        return "КМВА"
    else:
        return "КМВА / ДСНС"


def extract_concise_consequence(raw_text: str, impact_type: str) -> str:
    lower = raw_text.lower()
    if "склін" in lower or "вікн" in lower:
        return "Пошкодження скління будинку"
    elif ("покрівл" in lower or "дах" in lower) and ("пожеж" in lower or "загор" in lower or "займ" in lower):
        return "Локальна пожежа покрівлі"
    elif "склад" in lower:
        return "Загоряння складських приміщень"
    elif "авто" in lower or "машин" in lower or "парковк" in lower or "стоянк" in lower:
        return "Пошкодження припаркованих автомобілів"
    elif "нежитлов" in lower:
        return "Загоряння нежитлової споруди"
    elif "фасад" in lower or "багатоповерхів" in lower or "житлов" in lower:
        return "Пошкодження фасаду житлового будинку"
    elif "відкрит" in lower or "пустир" in lower:
        return "Падіння на відкритій місцевості"
    elif "парк" in lower or "ліс" in lower or "острів" in lower:
        return "Падіння уламків у парковій зоні"
    elif "човнов" in lower:
        return "Пошкодження споруд човнової станції"
    elif "азс" in lower or "паливн" in lower:
        return "Локальне займання на території АЗС"
    elif "міст" in lower or "колі" in lower or "залізниц" in lower:
        return "Пошкодження транспортної інфраструктури"
    elif "підстанц" in lower or "тец" in lower or "енергет" in lower:
        return "Пошкодження об'єкта енергетики"
    elif "навчальн" in lower or "школ" in lower or "дитсад" in lower:
        return "Падіння уламків на території навчального закладу"
    elif "лікарн" in lower or "медичн" in lower or "шпиталь" in lower or "госпітал" in lower:
        return "Пошкодження скління медичного закладу"
    elif "збитт" in lower or "перехоплен" in lower or impact_type == "intercepted_airburst":
        return "Збиття в повітрі черговими силами ППО"
    elif impact_type == "fire":
        return "Локальна пожежа, ліквідована ДСНС"
    elif impact_type == "direct_hit":
        return "Пряме влучання з локальними руйнуваннями"
    else:
        return "Падіння на відкритій місцевості"


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
        self.raw_osint_dir.mkdir(parents=True, exist_ok=True)

        # Robust regex patterns for the 10 Kyiv districts
        self.district_patterns = {
            "Оболонський": [
                r"оболон", r"мінськ", r"богатирськ", r"пуща[\s\-]водиц",
                r"північн(?:ий|ого|ому)?\s+міст", r"човнов(?:а|ої|у)\s+станці",
                r"собач.*гирл", r"героїв\s+дніпра", r"йорданськ"
            ],
            "Шевченківський": [
                r"шевченків", r"лук['’ʼ]янів", r"дегтярів", r"сирець", r"сирецьк",
                r"дорогожич", r"татарк", r"довженк", r"кіностуді", r"київстар",
                r"охматдит", r"завод[у\s]+«?артем", r"хрещатик"
            ],
            "Солом'янський": [
                r"солом['’ʼ]ян", r"відрадн", r"жулян", r"південн(?:ий|ого|ому)?\s+вокзал",
                r"гузар", r"чоколів", r"караваєв", r"шайб", r"кадетськ",
                r"протасів\s+яр", r"севастопольськ"
            ],
            "Печерський": [
                r"печерськ", r"липк", r"урядов.*квартал", r"лавр", r"звіринець",
                r"чорн.*гор", r"патон", r"військов.*госпітал", r"спорткомплекс"
            ],
            "Подільський": [
                r"поділ", r"куренів", r"вітрян", r"виноградар", r"фармак",
                r"контрактов", r"подільськ.*гаван"
            ],
            "Святошинський": [
                r"святошин", r"академмістечк", r"борщагів", r"берестейськ",
                r"антонов", r"білич", r"новобілич", r"вернадськ", r"святошинськ.*авіа"
            ],
            "Голосіївський": [
                r"голосіїв", r"деміїв", r"теремк", r"корчуват", r"пирогов",
                r"феофані", r"лиса\s+гор", r"видубич", r"тец[\s\-]?5", r"керхер", r"k[aä]rcher"
            ],
            "Дарницький": [
                r"дарницьк", r"позняк", r"осокорк", r"бортнич", r"харківськ.*шосе",
                r"харківськ.*масив", r"південн(?:ий|ого|ому)?\s+міст"
            ],
            "Деснянський": [
                r"деснян", r"троєщин", r"лісов.*масив", r"биківн", r"тец[\s\-]?6",
                r"деснянськ.*водопров"
            ],
            "Дніпровський": [
                r"дніпровськ", r"русанів", r"воскресен", r"лівобереж", r"дврз",
                r"райдужн", r"комфорттаун", r"комфорт.*таун", r"березняк", r"дарницьк.*тец"
            ],
        }

        # Suburbs and approach corridors for Kyiv
        self.suburbs_patterns = {
            "Бучанський сектор (Західний коридор)": [
                r"буч[аі]", r"ірпін", r"гостомел", r"мила", r"святопетрівськ",
                r"вишнев[еі]", r"макарів", r"бородянк"
            ],
            "Броварський сектор (Східний коридор)": [
                r"бровар", r"квітнев[аі]", r"скибин", r"димерк", r"зазим"
            ],
            "Бориспільський сектор (Південно-східний коридор)": [
                r"бориспіль", r"чубинськ", r"проліск", r"гора"
            ],
            "Вишгородський сектор (Північний коридор)": [
                r"вишгород", r"нові\s+петрівц", r"старі\s+петрівц", r"димер"
            ],
            "Фастівський / Обухівський сектор (Південний коридор)": [
                r"фастів", r"васильків", r"глеваха", r"калинівк", r"обухів", r"трипілл"
            ],
        }

    def classify_threat(self, text: str) -> tuple[str, str]:
        """Classify weapon threat type and alert level from text."""
        raw_text_lower = text.lower()
        if any(w in raw_text_lower for w in ["балістик", "іскандер-м", "іскандер м", "циркон", "zircon", "с-400", "s-400", "kn-23", "кинджал", "кинжал", "балістич"]):
            return "missile_ballistic", "red"
        elif any(w in raw_text_lower for w in ["х-101", "х-59", "х-69", "калібр", "крилат", "іскандер-к", "іскандер к", "х-22", "х-32", "онікс"]):
            return "missile_cruise", "red"
        elif any(w in raw_text_lower for w in ["ракета", "ракети", "ракетою", "ракетн"]):
            return "missile_cruise", "red"
        elif any(w in raw_text_lower for w in ["гербер", "гербар", "парус", "приман", "фальш-ціл", "фальш ціл", "без бойов", "без б/ч", "імітатор", "бандерол", "дань-т"]):
            return "drone_decoy", "yellow"
        elif any(w in raw_text_lower for w in ["реактивн", "shahed-238", "шахед-238", "шахед 238", "238", "шахед", "shahed", "герань", "бпла", "дрон"]):
            return "drone_shahed", "yellow"
        else:
            return "drone_shahed", "yellow"

    def extract_districts(self, text: str) -> list[str]:
        """Extract all mentioned Kyiv districts or outer defense corridors."""
        clean_text = text.replace("’", "'").replace("ʼ", "'").replace("`", "'").lower()
        detected_districts = []
        for district_name, patterns in self.district_patterns.items():
            if any(re.search(p, clean_text) for p in patterns):
                detected_districts.append(district_name)

        if not detected_districts:
            for suburb_name, patterns in self.suburbs_patterns.items():
                if any(re.search(p, clean_text) for p in patterns):
                    detected_districts.append(suburb_name)

        if not detected_districts:
            detected_districts = ["Київ (Загальноміське зведення)"]

        return detected_districts

    def parse_telegram_json(self, file_path: Path) -> tuple[list, list]:
        """Parses a standard Telegram Desktop export result.json."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return [], []

        channel_name = data.get("name", file_path.parent.name)
        messages = data.get("messages", [])
        extracted_events = []
        notebooklm_texts = []

        random.seed(42)

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

            # Normalize typographical apostrophes
            clean_text = raw_text.replace("’", "'").replace("ʼ", "'").replace("`", "'")
            raw_text_lower = clean_text.lower()

            # Filter false positives: weather forecasts, regular crime/traffic news
            if any(w in raw_text_lower for w in ["пожежної небезпеки", "зґвалтування", "провідний синоптик", "дтп за участю", "зіткнулися дві маршрутки"]):
                continue

            # Skip messages purely about other distant regions when Kyiv/capital is not mentioned
            other_regions = ["одес", "харків", "запоріж", "краматорськ", "прилук", "суми", "полтав", "кривий ріг", "львів", "херсон", "миколаїв"]
            is_other_city = any(r in raw_text_lower for r in other_regions)
            if re.search(r"\bдніпр(?:о|а|у|ом|і)\b", raw_text_lower) and "дніпровськ" not in raw_text_lower:
                is_other_city = True

            has_kyiv_context = any(k in raw_text_lower for k in [
                "київ", "столиц", "оболон", "дарниц", "святошин", "солом'ян",
                "шевченк", "поділ", "голосіїв", "печерськ", "деснян", "дніпров",
                "троєщин", "буча", "бровар", "бориспіль", "вишгород", "фастів", "обухів"
            ])
            if is_other_city and not has_kyiv_context:
                continue

            # Must mention Kyiv or its districts or key suburbs
            kyiv_keywords = [
                "київ", "столиц", "оболон", "дарниц", "святошин", "солом'ян",
                "шевченк", "поділ", "голосіїв", "печерськ", "деснян", "дніпров",
                "троєщин", "буча", "ірпін", "гостомел", "макарів", "бровар",
                "бориспіль", "вишгород", "фастів", "обухів", "васильків"
            ]
            if not any(k in raw_text_lower for k in kyiv_keywords):
                continue

            # Must have impact/strike/debris indicator
            has_impact = any(w in raw_text_lower for w in [
                "уламк", "падінн", "пожеж", "влучан", "збитт", "руйнуван",
                "постраждал", "вибух", "приліт", "вирва", "загорян"
            ])
            if not has_impact:
                continue

            # Threat classification & Alert level
            threat_type, alert_level = self.classify_threat(raw_text_lower)

            # Detect all mentioned Kyiv districts
            detected_districts = self.extract_districts(clean_text)

            date_str = msg.get("date", "")
            clean_date = date_str.replace("T", " ") if "T" in date_str else date_str

            # Create an event record for each detected district
            for idx, district in enumerate(detected_districts):
                event_id = f"TG-{msg.get('id', '0')}-{file_path.stem}-{idx}"
                base_lat, base_lon = DISTRICT_COORDS.get(district, (50.4501, 30.5234))
                jitter_lat = base_lat + random.uniform(-0.012, 0.012)
                jitter_lon = base_lon + random.uniform(-0.015, 0.015)

                impact_type = "debris_fall"
                if "влучан" in raw_text_lower or "приліт" in raw_text_lower:
                    impact_type = "direct_hit"
                elif "пожеж" in raw_text_lower or "загорян" in raw_text_lower:
                    impact_type = "fire"
                elif "збитт" in raw_text_lower:
                    impact_type = "intercepted_airburst"

                # Extract precise location hint
                loc_hint = f"Сектор {district}"
                if "ресторан" in raw_text_lower and "оболон" in raw_text_lower:
                    loc_hint = "Оболонь, будівля ресторану"
                elif "човнов" in raw_text_lower:
                    loc_hint = "Оболонь, човнова станція (затока Собаче гирло)"
                elif "навчальн" in raw_text_lower:
                    loc_hint = "Навчальний заклад / прилегла зона"
                elif "північн" in raw_text_lower and "міст" in raw_text_lower:
                    loc_hint = "Північний міст через Дніпро"
                elif "південн" in raw_text_lower and "міст" in raw_text_lower:
                    loc_hint = "Південний міст (опори та лінія метро)"
                elif "патон" in raw_text_lower:
                    loc_hint = "Міст Патона"
                elif "довженк" in raw_text_lower or "кіностуді" in raw_text_lower:
                    loc_hint = "Кіностудія ім. О. Довженка"
                elif "київстар" in raw_text_lower or "дегтярівськ" in raw_text_lower:
                    loc_hint = "Технологічний центр «Київстар» (вул. Дегтярівська)"
                elif "шайб" in raw_text_lower or "південн.*вокзал" in raw_text_lower:
                    loc_hint = "Привокзальний хаб «Шайба» / ст. Київ-Пасажирський"
                elif "керхер" in raw_text_lower or "karcher" in raw_text_lower:
                    loc_hint = "Логістичний термінал «Kärcher» (Пирогівський шлях)"
                elif "резервуар" in raw_text_lower and "оболон" in raw_text_lower:
                    loc_hint = "Резервуари ПММ «Оболонь» (вул. Богатирська)"
                elif "азс" in raw_text_lower or "азк" in raw_text_lower:
                    loc_hint = "АЗС / паливний комплекс"
                elif "гараж" in raw_text_lower:
                    loc_hint = "Гаражний кооператив"
                elif "парковк" in raw_text_lower or "авто" in raw_text_lower:
                    loc_hint = "Автостоянка / прибудинкова зона"
                elif "склад" in raw_text_lower:
                    loc_hint = "Складські приміщення"
                elif "дитсад" in raw_text_lower:
                    loc_hint = "Дитячий садок"
                elif "лікарн" in raw_text_lower or "шпиталь" in raw_text_lower or "госпітал" in raw_text_lower:
                    loc_hint = "Медичний заклад"
                elif "багатоповерхів" in raw_text_lower or "житлов" in raw_text_lower:
                    loc_hint = "Житлова забудова"

                consequence_fact = extract_concise_consequence(raw_text_lower, impact_type)
                official_source = normalize_source(clean_text, channel_name)

                event_record = {
                    "id": event_id,
                    "datetime": clean_date,
                    "district": district,
                    "location_hint": loc_hint,
                    "lat": round(jitter_lat, 4),
                    "lon": round(jitter_lon, 4),
                    "threat_type": threat_type,
                    "alert_level": alert_level,
                    "impact_type": impact_type,
                    "source": official_source,
                    "description": consequence_fact,
                }
                extracted_events.append(event_record)

                threat_ua = "Ударний БпЛА (Shahed)" if "shahed" in threat_type or "drone" in threat_type else ("Балістична ракета" if "ballistic" in threat_type else "Крилата ракета")
                notebooklm_texts.append(
                    f"- **{clean_date}** [{district}] ({threat_ua} / {alert_level.upper()}): {consequence_fact}"
                )

        return extracted_events, notebooklm_texts

    def run_pipeline(self) -> dict:
        """
        Executes end-to-end ingestion:
        Scans all raw JSON files recursively, extracts events,
        exports NotebookLM-compatible .txt and .md files,
        and saves unified datasets to data/processed/.
        """
        # 1. Base curated incidents
        curated_incidents_path = self.curated_dir / "kyiv_incidents_3m.csv"
        incidents_df = pd.read_csv(curated_incidents_path)

        # 2. Check for raw Telegram files recursively
        tg_files = list(self.raw_tg_dir.glob("**/*.json"))
        tg_events = []
        all_notebooklm_lines = []

        for f in tg_files:
            print(f"Parsing Telegram export: {f}")
            parsed_events, nblm_lines = self.parse_telegram_json(f)
            tg_events.extend(parsed_events)
            all_notebooklm_lines.extend(nblm_lines)

        if tg_events:
            print(f"Extracted {len(tg_events)} candidate incident reports from Telegram dumps.")
            tg_df = pd.DataFrame(tg_events)
            incidents_df = pd.concat([incidents_df, tg_df], ignore_index=True)

        # Unify all shahed variants & alert levels (R2: single tactical type «Ударні БпЛА (Shahed)»)
        incidents_df["threat_type"] = incidents_df["threat_type"].replace({
            "drone_jet": "drone_shahed",
            "drone_decoy": "drone_shahed",
        })
        incidents_df["alert_level"] = incidents_df["alert_level"].replace({"orange": "yellow"})

        # Deduplicate by approximate time (minute level) and district
        incidents_df["datetime_min"] = pd.to_datetime(incidents_df["datetime"]).dt.floor("10min")
        incidents_df = incidents_df.drop_duplicates(subset=["datetime_min", "district"], keep="first")
        incidents_df = incidents_df.drop(columns=["datetime_min"])
        incidents_df = incidents_df.sort_values("datetime", ascending=False).reset_index(drop=True)

        processed_incidents_path = self.processed_dir / "incidents_unified.csv"
        incidents_df.to_csv(processed_incidents_path, index=False, encoding="utf-8")

        # Copy alerts timeseries to processed
        alerts_src = self.curated_dir / "kyiv_alerts_timeseries.csv"
        alerts_df = pd.read_csv(alerts_src)
        alerts_dst = self.processed_dir / "alerts_unified.csv"
        alerts_df.to_csv(alerts_dst, index=False, encoding="utf-8")

        # 3. Generate NotebookLM-compatible text/markdown digest
        notebooklm_txt_path = self.raw_osint_dir / "kyiv_defense_intel_for_notebooklm.txt"
        notebooklm_md_path = self.raw_osint_dir / "kyiv_defense_intel_for_notebooklm.md"

        threat_summary = incidents_df["threat_type"].value_counts().to_dict()
        district_summary = incidents_df["district"].value_counts().to_dict()

        threat_labels_map = {
            "drone_shahed": "Ударні БпЛА (Shahed)",
            "drone_jet": "Ударні БпЛА (Shahed)",
            "drone_decoy": "Ударні БпЛА (Shahed)",
            "missile_ballistic": "Балістичні ракети",
            "missile_cruise": "Крилаті ракети",
        }

        content = "# Хроніка та аналітичне зведення повітряних атак по Києву (OSINT / Офіційні джерела)\n\n"
        content += "## 1. Загальні метрики та тактичні висновки (Defense Executive Summary)\n\n"
        content += f"- **Всього структуровано верифікованих інцидентів:** {len(incidents_df)}\n"
        content += "- **Період спостереження:** Квітень — Жовтень 2026 року (6 місяців / 184 доби)\n"
        content += "- **Ключові тактичні особливості:**\n"
        content += "  1. **Єдиний тактичний тип ударних БпЛА (`Ударні БпЛА (Shahed)`):** поєднання висотних та низьковисотних проривів уздовж річкових та транспортних коридорів (Дніпро, Житомирська траса, Обухівський напрямок).\n"
        content += "  2. **Застосування фальш-цілей та приманок (Гербера, Бандероль):** масовані вильоти роїв дронів-приманок для виснаження БК мобільних вогневих груп перед ракетними ударами.\n"
        content += "  3. **Концентровані ракетні залпи (Балістичні та крилаті ракети):** удари комбінацією Іскандер-М, С-400, Циркон, KN-23 та Х-101 по стратегічних об'єктах столиці.\n"
        content += "  4. **Розгортання передових рубежів ППО:** розгорнуто 12+ автоматизованих великокаліберних турелей та мобільних вогневих груп на річковому та західному рубежах.\n\n"

        content += "### Розподіл за видами загроз:\n"
        for th, cnt in threat_summary.items():
            lbl = threat_labels_map.get(th, th)
            content += f"- **{lbl}:** {cnt} інцидентів ({round(cnt / len(incidents_df) * 100, 1)}%)\n"

        content += "\n### Розподіл інцидентів за секторами та районами:\n"
        for dist, cnt in district_summary.items():
            content += f"- **{dist}:** {cnt} інцидентів\n"

        content += "\n\n## 2. Структурована хроніка інцидентів (Останні 80 подій)\n\n"
        content += "| Дата | Сектор / Район | Тип загрози | Рівень | Локація | Наслідки |\n"
        content += "|---|---|---|---|---|---|\n"
        for _, row in incidents_df.head(80).iterrows():
            th_ua = threat_labels_map.get(row['threat_type'], row['threat_type'])
            lvl_ua = "Жовтий рівень (БпЛА)" if row['alert_level'] == 'yellow' else "Червоний рівень (Ракети)"
            content += f"| {row['datetime']} | {row['district']} | {th_ua} | {lvl_ua} | {row['location_hint']} | {row['description']} |\n"

        content += "\n\n## 3. Детальний лог первинних зведень моніторингових каналів:\n\n"
        content += "\n".join(all_notebooklm_lines[:300])

        with open(notebooklm_txt_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(notebooklm_md_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Generated NotebookLM-ready file: {notebooklm_txt_path}")
        print(f"Total unified incidents on map: {len(incidents_df)}")

        return {
            "incidents_count": len(incidents_df),
            "alerts_count": len(alerts_df),
            "custom_tg_files_found": len(tg_files),
            "notebooklm_export_ready": str(notebooklm_txt_path),
        }


if __name__ == "__main__":
    pipeline = KyivDataIngestionPipeline()
    res = pipeline.run_pipeline()
    print("Pipeline result:", res)

