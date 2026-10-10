"""
map_builder.py
Generates the standalone, interactive Kyiv Defense Map & Analytics Dashboard (index.html).
Features:
- Google Maps (Roadmap + Satellite) & Dark Tactical Tile switchers.
- Yellow (Drones/Shahed) vs Red (Missiles/Ballistics) vs All Threats mode toggling.
- Infrastructure Category filtering (Energy, Transport/Bridges, Admin, Defense).
- Popups with multi-factor Risk Scores (0-100), vulnerability, and descriptions.
- District Safety Rankings leaderboard and 3-month incident points.
- Embedded Time Series analytics drawer with leak-free evaluation metrics.
"""

import json
import sys
from pathlib import Path
from jinja2 import Template

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.risk_engine import KyivRiskEngine
from src.time_series import KyivAlertTimeSeriesAnalyzer


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Київ: Оборонний моніторинг загроз та аналіз часових рядів</title>
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" />
    <style>
        :root {
            --bg-dark: #0f172a;
            --panel-bg: rgba(15, 23, 42, 0.85);
            --border-color: rgba(255, 255, 255, 0.12);
            --accent-yellow: #eab308;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        body, html {
            height: 100%;
            width: 100%;
            overflow: hidden;
            background-color: var(--bg-dark);
            color: var(--text-main);
        }

        #map {
            height: 100%;
            width: 100%;
            z-index: 1;
        }

        /* Top Header Bar */
        .top-navbar {
            position: absolute;
            top: 16px;
            left: 16px;
            right: 16px;
            z-index: 1000;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            padding: 12px 20px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
        }

        .title-block {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .title-badge {
            background: linear-gradient(135deg, #1e3a8a, #0284c7);
            color: white;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            padding: 5px 10px;
            border-radius: 8px;
        }

        .title-text h1 {
            font-size: 17px;
            font-weight: 700;
            color: #ffffff;
        }

        .title-text p {
            font-size: 12px;
            color: var(--text-muted);
        }

        /* Threat Mode Selector */
        .threat-modes {
            display: flex;
            gap: 8px;
            background: rgba(0, 0, 0, 0.35);
            padding: 4px;
            border-radius: 10px;
        }

        .mode-btn {
            border: none;
            background: transparent;
            color: var(--text-muted);
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .mode-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
        }

        .mode-btn.active[data-mode="all"] {
            background: #334155;
            color: #f8fafc;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }

        .mode-btn.active[data-mode="yellow"] {
            background: #ca8a04;
            color: #ffffff;
            box-shadow: 0 0 14px rgba(234, 179, 8, 0.4);
        }

        .mode-btn.active[data-mode="red"] {
            background: #dc2626;
            color: #ffffff;
            box-shadow: 0 0 14px rgba(239, 68, 68, 0.4);
        }

        .header-actions {
            display: flex;
            gap: 10px;
        }

        .btn-action {
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
            border: 1px solid var(--border-color);
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .btn-action:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* Side Panel */
        .side-panel {
            position: absolute;
            top: 86px;
            right: 16px;
            bottom: 24px;
            width: 380px;
            z-index: 1000;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            border-radius: 14px;
            border: 1px solid var(--border-color);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: transform 0.3s ease;
        }

        .panel-tabs {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.2);
        }

        .panel-tab {
            flex: 1;
            padding: 12px;
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-muted);
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }

        .panel-tab.active {
            color: #ffffff;
            border-bottom-color: var(--accent-blue);
            background: rgba(255, 255, 255, 0.03);
        }

        .panel-content {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }

        .tab-pane {
            display: none;
        }

        .tab-pane.active {
            display: block;
        }

        /* Filter Section */
        .filter-section {
            margin-bottom: 18px;
        }

        .section-title {
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .category-filters {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }

        .filter-chip {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 12px;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.2s;
            user-select: none;
        }

        .filter-chip.active {
            background: rgba(59, 130, 246, 0.2);
            border-color: var(--accent-blue);
            color: #ffffff;
        }

        /* Leaderboard & Stats Cards */
        .stat-card {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .stat-card:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.25);
            transform: translateX(-2px);
        }

        .district-info h4 {
            font-size: 14px;
            font-weight: 600;
            color: #f1f5f9;
        }

        .district-info p {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .score-pill {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
        }

        /* Map Legend Overlay */
        .map-legend {
            position: absolute;
            bottom: 24px;
            left: 16px;
            z-index: 1000;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            font-size: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .legend-color {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }

        /* Custom Popup Styling */
        .leaflet-popup-content-wrapper {
            background: #1e293b !important;
            color: #f8fafc !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5) !important;
        }

        .leaflet-popup-tip {
            background: #1e293b !important;
        }

        .popup-title {
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 4px;
            color: #ffffff;
        }

        .popup-cat {
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
            color: var(--accent-blue);
            margin-bottom: 8px;
        }

        .popup-score-box {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(0, 0, 0, 0.3);
            padding: 8px 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .popup-score-num {
            font-size: 18px;
            font-weight: 800;
        }

        .popup-desc {
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.4;
        }

        /* Time Series Modal Drawer */
        .analytics-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(8px);
            z-index: 2000;
            justify-content: center;
            align-items: center;
        }

        .analytics-modal.open {
            display: flex;
        }

        .modal-card {
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            width: 90%;
            max-width: 820px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 24px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 12px;
        }

        .btn-close {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 20px;
            cursor: pointer;
        }

        .btn-close:hover {
            color: #fff;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 24px;
        }

        .metric-card {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px;
            text-align: center;
        }

        .metric-val {
            font-size: 22px;
            font-weight: 800;
            color: #38bdf8;
            margin-bottom: 4px;
        }

        .metric-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        /* Base Tile Switcher in Map */
        .tile-selector {
            position: absolute;
            bottom: 24px;
            right: 410px;
            z-index: 1000;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 4px;
            display: flex;
            gap: 4px;
        }

        .tile-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
        }

        .tile-btn.active {
            background: var(--accent-blue);
            color: #ffffff;
        }

        /* Pulse Animation */
        @keyframes pulse-red {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        @keyframes pulse-yellow {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(234, 179, 8, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0); }
        }
        .pulse-marker-red {
            animation: pulse-red 2s infinite;
            border-radius: 50%;
        }
        .pulse-marker-yellow {
            animation: pulse-yellow 2s infinite;
            border-radius: 50%;
        }
    </style>
</head>
<body>

    <!-- Map Container -->
    <div id="map"></div>

    <!-- Top Navigation Bar -->
    <div class="top-navbar">
        <div class="title-block">
            <div class="title-badge">Defense OSINT</div>
            <div class="title-text">
                <h1>Kyiv Air Defense Risk Map</h1>
                <p>Аналіз часових рядів тривог та оцінка ризиків об'єктів інфраструктури</p>
            </div>
        </div>

        <!-- Threat Mode Switcher -->
        <div class="threat-modes">
            <button class="mode-btn active" data-mode="all" onclick="setThreatMode('all')">
                <i class="fa-solid fa-layer-group"></i> Всі загрози
            </button>
            <button class="mode-btn" data-mode="yellow" onclick="setThreatMode('yellow')">
                <i class="fa-solid fa-triangle-exclamation"></i> Жовтий (Шахеди / БПЛА)
            </button>
            <button class="mode-btn" data-mode="red" onclick="setThreatMode('red')">
                <i class="fa-solid fa-radiation"></i> Червоний (Ракети / Балістика)
            </button>
        </div>

        <div class="header-actions">
            <button class="btn-action" onclick="openAnalyticsModal()">
                <i class="fa-solid fa-chart-line"></i> Time Series Метрики
            </button>
        </div>
    </div>

    <!-- Tile Layer Switcher -->
    <div class="tile-selector">
        <button class="tile-btn active" data-tile="gmaps_road" onclick="setBaseTile('gmaps_road')">Google Maps</button>
        <button class="tile-btn" data-tile="gmaps_sat" onclick="setBaseTile('gmaps_sat')">Супутник</button>
        <button class="tile-btn" data-tile="carto_dark" onclick="setBaseTile('carto_dark')">Нічна карта</button>
    </div>

    <!-- Legend Overlay -->
    <div class="map-legend">
        <div style="font-weight:700; margin-bottom:4px; color:#cbd5e1;">Рівень небезпеки об'єкта:</div>
        <div class="legend-item"><div class="legend-color" style="background:#dc2626;"></div> 80-100: Критичний ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#f97316;"></div> 60-79: Високий ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#eab308;"></div> 40-59: Середній ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#10b981;"></div> 0-39: Помірний / Базовий</div>
        <div style="margin-top:6px; border-top:1px solid rgba(255,255,255,0.1); padding-top:4px;">
            <i class="fa-solid fa-location-crosshairs" style="color:#f43f5e"></i> Інциденти уламків/ударів (3 міс)
        </div>
    </div>

    <!-- Side Intelligence Panel -->
    <div class="side-panel">
        <div class="panel-tabs">
            <div class="panel-tab active" onclick="switchPanelTab('tab-districts')">Райони Києва</div>
            <div class="panel-tab" onclick="switchPanelTab('tab-objects')">Об'єкти & Фільтри</div>
            <div class="panel-tab" onclick="switchPanelTab('tab-incidents')">Хроніка ударів</div>
        </div>

        <div class="panel-content">
            <!-- Tab 1: District Rankings -->
            <div id="tab-districts" class="tab-pane active">
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-shield-halved"></i> Рейтинг безпеки районів</div>
                    <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
                        Розраховано на основі частоти ударів за 3 місяці та щільності стратегічних цілей.
                    </p>
                    <div id="districts-list">
                        <!-- Rendered by JS -->
                    </div>
                </div>
            </div>

            <!-- Tab 2: Objects & Filters -->
            <div id="tab-objects" class="tab-pane">
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-filter"></i> Категорії об'єктів</div>
                    <div class="category-filters">
                        <div class="filter-chip active" data-cat="energy" onclick="toggleCategoryFilter('energy')">
                            <i class="fa-solid fa-bolt" style="color:#eab308"></i> Енергетика (ТЕЦ)
                        </div>
                        <div class="filter-chip active" data-cat="transport" onclick="toggleCategoryFilter('transport')">
                            <i class="fa-solid fa-bridge" style="color:#38bdf8"></i> Мости / Транспорт
                        </div>
                        <div class="filter-chip active" data-cat="admin" onclick="toggleCategoryFilter('admin')">
                            <i class="fa-solid fa-landmark" style="color:#a855f7"></i> Влада / КМДА
                        </div>
                        <div class="filter-chip active" data-cat="industry" onclick="toggleCategoryFilter('industry')">
                            <i class="fa-solid fa-industry" style="color:#f43f5e"></i> Оборонні заводи
                        </div>
                    </div>
                </div>
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-list-check"></i> Перелік об'єктів під моніторингом</div>
                    <div id="objects-list">
                        <!-- Rendered by JS -->
                    </div>
                </div>
            </div>

            <!-- Tab 3: Incidents Log -->
            <div id="tab-incidents" class="tab-pane">
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-fire"></i> Зафіксовані уламки та удари за 3 міс</div>
                    <div id="incidents-list">
                        <!-- Rendered by JS -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Analytics Modal Drawer -->
    <div id="analyticsModal" class="analytics-modal">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 style="font-size:20px; font-weight:700;">Time Series Analysis & Валідація без Data Leakage</h2>
                    <p style="font-size:12px; color:var(--text-muted);">
                        Оцінка на найновішому тестовому періоді (Вересень — Жовтень) без заглядання у майбутнє.
                    </p>
                </div>
                <button class="btn-close" onclick="closeAnalyticsModal()">&times;</button>
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-val" id="metric-roc-auc">0.681</div>
                    <div class="metric-label">Model ROC-AUC (Holdout)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="metric-baseline-auc">0.647</div>
                    <div class="metric-label">Baseline Prior AUC</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="metric-brier">0.217</div>
                    <div class="metric-label">Brier Score (Калібрування)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="metric-alerts-cnt">99</div>
                    <div class="metric-label">Аналізовано тривог</div>
                </div>
            </div>

            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:12px; padding:16px; margin-bottom:18px;">
                <h3 style="font-size:14px; font-weight:700; margin-bottom:8px; color:#38bdf8;">
                    <i class="fa-solid fa-shield-virus"></i> Методологія запобігання Data Leakage (Вимога хакатону)
                </h3>
                <p style="font-size:13px; line-height:1.5; color:#cbd5e1;">
                    Датасет тривог розділено суворо хронологічно: навчальна вибірка (Train) включає дані до <b>1 вересня</b>, а тестова вибірка (Test) — найновіший період з <b>1 вересня по 10 жовтня</b>.<br>
                    Усі ознаки моделі (кількість тривог за попередні 24/72 год, час з моменту останньої тривоги, циклічні фази доби) на момент прогнозу $T$ обчислюються <b>виключно з інформації, відомої до моменту $T$</b>.
                </p>
            </div>

            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:12px; padding:16px;">
                <h3 style="font-size:14px; font-weight:700; margin-bottom:12px;">
                    <i class="fa-solid fa-clock"></i> Розподіл тривог за годинами доби (Часовий ряд Києва)
                </h3>
                <div style="display:flex; align-items:flex-end; gap:4px; height:120px; padding-top:10px;" id="hourly-chart">
                    <!-- Hourly bars populated by JS -->
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:11px; color:var(--text-muted);">
                    <span>00:00 (Нічний пік шахедів)</span>
                    <span>06:00 (Ранок)</span>
                    <span>12:00 (День)</span>
                    <span>18:00 (Вечір)</span>
                    <span>23:00</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <!-- Embedded Model Data -->
    <script>
        const RISK_DATA = {{ risk_data_json }};
        const TS_STATS = {{ ts_stats_json }};
        const TS_EVAL = {{ ts_eval_json }};
        const INCIDENTS_DATA = {{ incidents_json }};

        // Current state
        let currentThreatMode = 'all'; // 'all', 'yellow', 'red'
        let activeCategories = new Set(['energy', 'transport', 'admin', 'industry']);

        // Initialize Map
        const map = L.map('map', {
            center: [50.4501, 30.5234], // Kyiv Center
            zoom: 12,
            zoomControl: false
        });

        L.control.zoom({ position: 'bottomright' }).addTo(map);

        // Tile Layers
        const tileLayers = {
            gmaps_road: L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
                maxZoom: 20,
                attribution: '© Google Maps'
            }),
            gmaps_sat: L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
                maxZoom: 20,
                attribution: '© Google Satellite'
            }),
            carto_dark: L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
                attribution: '© CartoDB'
            })
        };

        let currentTile = tileLayers.gmaps_road;
        currentTile.addTo(map);

        function setBaseTile(tileKey) {
            map.removeLayer(currentTile);
            currentTile = tileLayers[tileKey];
            currentTile.addTo(map);
            document.querySelectorAll('.tile-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tile === tileKey);
            });
        }

        // Feature Layers
        let objectsLayerGroup = L.layerGroup().addTo(map);
        let incidentsLayerGroup = L.layerGroup().addTo(map);
        let districtsLayerGroup = L.layerGroup().addTo(map);

        function getScoreColor(score) {
            if (score >= 80) return '#dc2626'; // Red / Critical
            if (score >= 60) return '#f97316'; // Orange / High
            if (score >= 40) return '#eab308'; // Yellow / Medium
            return '#10b981'; // Green / Moderate
        }

        function getCategoryIcon(cat) {
            switch(cat) {
                case 'energy': return 'fa-bolt';
                case 'transport': return 'fa-bridge';
                case 'admin': return 'fa-landmark';
                case 'industry': return 'fa-industry';
                default: return 'fa-location-dot';
            }
        }

        // Render Infrastructure Objects
        function renderObjects() {
            objectsLayerGroup.clearLayers();

            RISK_DATA.objects.forEach(obj => {
                if (!activeCategories.has(obj.category)) return;

                const scoreObj = obj.scores[currentThreatMode];
                const score = scoreObj.score;
                const tier = scoreObj.tier;
                const color = getScoreColor(score);

                // Custom marker
                const iconHtml = `
                    <div style="background:${color}; width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; border:2px solid white; box-shadow:0 3px 10px rgba(0,0,0,0.5);">
                        <i class="fa-solid ${getCategoryIcon(obj.category)}" style="font-size:13px;"></i>
                    </div>
                `;

                const customIcon = L.divIcon({
                    html: iconHtml,
                    className: (currentThreatMode === 'red' && score >= 75) ? 'pulse-marker-red' : (currentThreatMode === 'yellow' && score >= 75 ? 'pulse-marker-yellow' : ''),
                    iconSize: [32, 32],
                    iconAnchor: [16, 16]
                });

                const marker = L.marker([obj.lat, obj.lon], { icon: customIcon });

                const popupContent = `
                    <div class="popup-title">${obj.name}</div>
                    <div class="popup-cat"><i class="fa-solid ${getCategoryIcon(obj.category)}"></i> ${obj.category.toUpperCase()} • ${obj.district}</div>
                    <div class="popup-score-box">
                        <span style="font-size:12px; color:#cbd5e1;">Індекс небезпеки (${currentThreatMode.toUpperCase()}):</span>
                        <span class="popup-score-num" style="color:${color};">${score}/100</span>
                    </div>
                    <div style="font-size:11px; margin-bottom:6px; color:#94a3b8;">
                        Статус: <b style="color:${color};">${tier}</b> | Близькість до уламків: +${scoreObj.proximity} б.
                    </div>
                    <div class="popup-desc">${obj.description}</div>
                `;

                marker.bindPopup(popupContent);
                objectsLayerGroup.addLayer(marker);
            });
        }

        // Render Incidents
        function renderIncidents() {
            incidentsLayerGroup.clearLayers();

            INCIDENTS_DATA.forEach(inc => {
                // Filter by mode
                if (currentThreatMode === 'yellow' && inc.alert_level !== 'yellow') return;
                if (currentThreatMode === 'red' && inc.alert_level !== 'red') return;

                const isDrone = inc.threat_type === 'drone_shahed';
                const incColor = isDrone ? '#f59e0b' : '#f43f5e';

                const incidentIcon = L.divIcon({
                    html: `<div style="background:${incColor}; width:16px; height:16px; border-radius:50%; border:2px solid #ffffff; box-shadow:0 0 8px ${incColor};"></div>`,
                    className: '',
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });

                const marker = L.marker([inc.lat, inc.lon], { icon: incidentIcon });
                const popup = `
                    <div class="popup-title"><i class="fa-solid fa-triangle-exclamation" style="color:${incColor}"></i> Подія: ${inc.location_hint}</div>
                    <div class="popup-cat">${inc.district} • ${inc.datetime}</div>
                    <div style="font-size:12px; margin-bottom:6px;">
                        Тип загрози: <b>${inc.threat_type}</b> (${inc.alert_level.toUpperCase()})<br>
                        Наслідки: <b>${inc.impact_type}</b><br>
                        Джерело: <i>${inc.source}</i>
                    </div>
                    <div class="popup-desc">${inc.description}</div>
                `;
                marker.bindPopup(popup);
                incidentsLayerGroup.addLayer(marker);
            });
        }

        // Threat Mode Handler
        function setThreatMode(mode) {
            currentThreatMode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.mode === mode);
            });
            renderObjects();
            renderIncidents();
            renderObjectsList();
        }

        // Category Filter Handler
        function toggleCategoryFilter(cat) {
            const chip = document.querySelector(`.filter-chip[data-cat="${cat}"]`);
            if (activeCategories.has(cat)) {
                activeCategories.delete(cat);
                chip.classList.remove('active');
            } else {
                activeCategories.add(cat);
                chip.classList.add('active');
            }
            renderObjects();
            renderObjectsList();
        }

        // UI Tabs & Side Lists
        function switchPanelTab(tabId) {
            document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            event.currentTarget.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }

        function renderDistrictsList() {
            const container = document.getElementById('districts-list');
            container.innerHTML = '';
            RISK_DATA.districts.forEach(d => {
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([d.center_lat, d.center_lon], 13);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>#${d.threat_rank} ${d.district}</h4>
                        <p>${d.status} • Інцидентів: ${d.incidents_count}</p>
                    </div>
                    <div class="score-pill" style="background:${d.badge_color}33; color:${d.badge_color}; border:1px solid ${d.badge_color};">
                        ${d.safety_score} безпека
                    </div>
                `;
                container.appendChild(card);
            });
        }

        function renderObjectsList() {
            const container = document.getElementById('objects-list');
            container.innerHTML = '';
            const filtered = RISK_DATA.objects.filter(o => activeCategories.has(o.category));
            filtered.forEach(obj => {
                const score = obj.scores[currentThreatMode].score;
                const color = getScoreColor(score);
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([obj.lat, obj.lon], 15);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>${obj.name}</h4>
                        <p>${obj.district} • ${obj.category.toUpperCase()}</p>
                    </div>
                    <div class="score-pill" style="background:${color}33; color:${color}; border:1px solid ${color};">
                        ${score}
                    </div>
                `;
                container.appendChild(card);
            });
        }

        function renderIncidentsList() {
            const container = document.getElementById('incidents-list');
            container.innerHTML = '';
            INCIDENTS_DATA.forEach(inc => {
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([inc.lat, inc.lon], 15);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>${inc.district}</h4>
                        <p>${inc.datetime.split(' ')[0]} • ${inc.location_hint}</p>
                    </div>
                    <span style="font-size:11px; padding:3px 8px; border-radius:6px; background:#334155; color:#cbd5e1;">
                        ${inc.threat_type.replace('drone_', '').replace('missile_', '')}
                    </span>
                `;
                container.appendChild(card);
            });
        }

        // Modal Handlers
        function openAnalyticsModal() {
            document.getElementById('analyticsModal').classList.add('open');
            renderHourlyChart();
        }

        function closeAnalyticsModal() {
            document.getElementById('analyticsModal').classList.remove('open');
        }

        function renderHourlyChart() {
            const chart = document.getElementById('hourly-chart');
            chart.innerHTML = '';
            const dist = TS_STATS.hourly_onset_distribution;
            const maxVal = Math.max(...dist, 1);

            dist.forEach((val, hour) => {
                const heightPct = (val / maxVal) * 100;
                const isNightPeak = (hour >= 23 || hour <= 5);
                const col = isNightPeak ? '#ca8a04' : '#38bdf8';
                const bar = document.createElement('div');
                bar.style.flex = '1';
                bar.style.height = `${Math.max(8, heightPct)}%`;
                bar.style.background = col;
                bar.style.borderRadius = '3px 3px 0 0';
                bar.title = `${hour}:00 - ${val} тривог`;
                chart.appendChild(bar);
            });
        }

        // Initial Boot
        renderObjects();
        renderIncidents();
        renderDistrictsList();
        renderObjectsList();
        renderIncidentsList();
    </script>
</body>
</html>
"""


def build_dashboard():
    # 1. Compute Risk Data
    risk_engine = KyivRiskEngine()
    risk_data = risk_engine.calculate_risk_scores()

    # 2. Compute Time Series Analytics
    ts_analyzer = KyivAlertTimeSeriesAnalyzer()
    ts_stats = ts_analyzer.compute_descriptive_stats()
    ts_eval = ts_analyzer.run_temporal_evaluation()

    # 3. Load incidents
    incidents_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "curated"
        / "kyiv_incidents_3m.csv"
    )
    incidents_df = risk_engine.incidents_df
    incidents_list = incidents_df.to_dict(orient="records")

    # 4. Render Jinja template
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        risk_data_json=json.dumps(risk_data, ensure_ascii=False),
        ts_stats_json=json.dumps(ts_stats, ensure_ascii=False),
        ts_eval_json=json.dumps(ts_eval, ensure_ascii=False),
        incidents_json=json.dumps(incidents_list, ensure_ascii=False),
    )

    out_file = Path(__file__).resolve().parent.parent / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Interactive Dashboard successfully built at: {out_file}")
    return out_file


if __name__ == "__main__":
    build_dashboard()
