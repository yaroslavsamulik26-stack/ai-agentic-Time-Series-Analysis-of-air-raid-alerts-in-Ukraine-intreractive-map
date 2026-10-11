# Kyiv Air Defense Risk Map & Time Series Analytics

> **Mini Pet-Project in Python solving a real-world defense challenge:** Spatio-temporal risk forecasting and intelligence mapping of air raid alerts in Kyiv, Ukraine.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Evaluation](https://img.shields.io/badge/Evaluation-Zero%20Data%20Leakage-success.svg)
![Map](https://img.shields.io/badge/Map-Leaflet%20%7C%20Google%20Maps%20Tiles-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 🎯 Overview & Defense Problem Solved

During Russian air attacks on Kyiv, citizens and defense analysts face distinct threat profiles depending on the weapon type:
- **🟡 Yellow Alert Mode (Shahed / Strike Drones):** Concentrated during night hours (23:00 – 06:00), targeting energy substations, thermal power plants (TECs), and fuel/logistics hubs. High risk of debris fall across flight approach corridors.
- **🔴 Red Alert Mode (Cruise Missiles, Ballistics, Kinzhal / Tu-95MS):** Sudden daylight or early-morning strikes targeting decision centers (government quarter), bridges over the Dnipro, defense industry plants (Artem, Luch), and Kyiv Hydroelectric Station (HES).

This project combines **leak-free Time Series forecasting** of alert hazard probabilities with a **Geospatial Multi-Criteria Risk Scoring Engine** and an **interactive, standalone map dashboard** with Google Maps tiles.

---

## 🚀 Key Features

1. **Strict Leak-Free Time Series Modeling (Zero Data Leakage):**
   - Chronological temporal train/test split: Training on alerts up to August 31, 2026; holdout evaluation on September 1 – October 10, 2026.
   - All features at time $T$ (historical alert density, time elapsed since previous raid, cyclical harmonic diurnal phases) are strictly backward-looking.
   - Outperforms baseline empirical frequency: **ROC-AUC: 0.681** (vs Baseline: 0.647), **Brier Score: 0.217**.
2. **Multi-Factor Facility Risk Scoring ($0–100$):**
   - Real-time risk index for 35+ critical Kyiv infrastructure facilities across energy (TECs, substations), transport (bridges, railway hubs), administration, and defense manufacturing.
   - Incorporates spatial kernel proximity decay to confirmed strike/debris points over the past 3 months.
3. **Calibrated District Hazard Index & Gapless 10-District Coverage:**
   - 100% seamless, contiguous OpenStreetMap administrative polygons for all 10 Kyiv districts (Right and Left banks) with zero unpartitioned gaps.
   - Logarithmically calibrated risk scoring reflecting actual strike distribution (from quietest districts with 9-13 strikes to most targeted central sectors with 260+ events).
4. **Interactive Standalone Web Dashboard (`index.html`):**
   - Built on Leaflet with Google Maps Roadmap and Google Satellite tiles.
   - Compact, closable, and draggable control headers.
   - Interactive incident time-range selector defaulting to the last 7 days (`7 днів`, `30 днів`, `Всі (3 міс)`).
   - Dynamic threat toggler: Yellow Threat (Shahed/drones), Red Threat (missiles/ballistics), and Combined.
   - Runs out-of-the-box in any browser with zero API keys or external server dependencies.
5. **Universal Multi-Source Ingestion (`src/parser.py`):**
   - Supports Telegram Desktop JSON exports (`result.json`), NotebookLM/Perplexity OSINT text and Markdown dumps, and official alerts archives.

---

## 📐 Mathematical Formulation

The risk score $\text{RiskScore}_i(m)$ for infrastructure facility $i$ under threat mode $m \in \{\text{Yellow}, \text{Red}\}$ is defined as:

$$\text{RiskScore}_i(m) = \min\left(100, \, w_{\text{vuln}} \cdot V_i(m) + w_{\text{prox}} \cdot P_i(m) + w_{\text{time}} \cdot T(h, m) + w_{\text{dist}} \cdot D_i\right)$$

Where:
- $V_i(m) \in [0, 40]$: Baseline facility vulnerability and target prioritization for weapon type $m$.
- $P_i(m) \in [0, 30]$: Spatial kernel proximity to confirmed impacts and debris falls over the last 90 days:
  $$P_i(m) = \sum_{j \in \text{Incidents}(m)} \exp\left(-\frac{\text{dist}(i, j)^2}{2\sigma^2}\right)$$
- $T(h, m) \in [0, 20]$: Time-series diurnal hazard coefficient for hour $h$ and weapon $m$.
- $D_i \in [0, 10]$: Historical incident density within the facility's administrative district.

---

## 📁 Repository Structure

```text
kyiv-air-defense-map/
├── data/
│   ├── raw/                           # Drop user Telegram & OSINT dumps here
│   │   ├── telegram/
│   │   └── osint/
│   ├── processed/                     # Unified and normalized datasets
│   └── curated/                       # Baseline verified datasets (works out-of-the-box)
│       ├── kyiv_infrastructure.geojson
│       ├── kyiv_districts.geojson
│       ├── kyiv_alerts_timeseries.csv
│       └── kyiv_incidents_3m.csv
├── src/
│   ├── parser.py                      # Multi-source data ingestion pipeline
│   ├── time_series.py                 # Time series model & leak-free evaluation
│   ├── risk_engine.py                 # Multi-criteria geospatial scoring engine
│   └── map_builder.py                 # Interactive dashboard compiler
├── main.py                            # End-to-end execution pipeline
├── index.html                         # Compiled standalone interactive dashboard
├── requirements.txt                   # Minimal dependencies (pandas, scikit-learn, jinja2)
├── SUBMISSION_REFLECTION.md           # ~100-word reflection for hackathon submission
└── README.md
```

---

## ⚡ Quick Start

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/YOUR_USERNAME/kyiv-air-defense-map.git
cd kyiv-air-defense-map

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Pipeline
```bash
python main.py
```
This runs the full ingestion, fits the time series model, evaluates on the holdout test period, computes all spatial risk scores, and compiles `index.html`.

### 3. Open Interactive Map
Double-click `index.html` in your file explorer or open it in your browser:
```bash
open index.html  # On macOS
```

---

## 📊 Time Series Evaluation Results (Test Holdout)

| Metric | Predictive Model | Historical Baseline | Status |
|---|---|---|---|
| **ROC-AUC** | **0.681** | 0.647 | Outperforms Baseline (+5.2%) |
| **Brier Score (Calibration)** | **0.217** | 0.231 | Well-calibrated probabilities |
| **Data Leakage Check** | Passed (Zero) | Passed (Zero) | Strict chronological cutoff |
| **Evaluation Period** | Sept 1 – Oct 9, 2026 | Sept 1 – Oct 9, 2026 | Most recent available period |

---

## 👥 Adding Custom Data
- **Telegram:** Export chat history from Telegram Desktop (`...` -> *Export chat history* -> *Machine-readable JSON* without media) and place the JSON in `data/raw/telegram/`.
- **Perplexity / NotebookLM:** Save your incident extraction table as a CSV in `data/raw/osint/`.
- Run `python main.py` to automatically ingest and update the map!
