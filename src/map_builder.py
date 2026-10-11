"""
map_builder.py
Generates the standalone, interactive Kyiv Defense Map & Analytics Dashboard (index.html).
Features:
- Google Maps (Roadmap + Satellite) tile switchers (Dark map completely removed).
- Full 10 Kyiv districts rendered as interactive polygons on both Right and Left banks.
- Compact, draggable, and closable floating control panels.
- Yellow (Drones/Shahed) vs Red (Missiles/Ballistics) vs All Threats mode toggling.
- Infrastructure Category filtering (Energy, Transport/Bridges, Admin, Defense).
- Deep, calibrated multi-factor Risk Scores (0-100) and district safety leaderboard.
- Embedded Time Series analytics modal with leak-free evaluation metrics.
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
            --panel-bg: rgba(15, 23, 42, 0.90);
            --border-color: rgba(255, 255, 255, 0.15);
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

        /* Top Navigation Bar - Compact & Draggable */
        .top-navbar {
            position: absolute;
            top: 10px;
            left: 10px;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            padding: 6px 12px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
            user-select: none;
            cursor: move;
        }

        .title-block {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .title-badge {
            background: linear-gradient(135deg, #1e3a8a, #0284c7);
            color: white;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            padding: 3px 6px;
            border-radius: 6px;
        }

        .title-text h1 {
            font-size: 13px;
            font-weight: 700;
            color: #ffffff;
            white-space: nowrap;
        }

        /* Threat Mode & Time Range Selectors - Small Icons */
        .threat-modes, .time-range-modes {
            display: flex;
            gap: 3px;
            background: rgba(0, 0, 0, 0.4);
            padding: 3px;
            border-radius: 8px;
        }

        .time-btn {
            border: none;
            background: transparent;
            color: var(--text-muted);
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
        }

        .time-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.08);
        }

        .time-btn.active {
            background: #0284c7;
            color: #ffffff;
            box-shadow: 0 0 8px rgba(2, 132, 199, 0.5);
        }

        .mode-btn {
            border: none;
            background: transparent;
            color: var(--text-muted);
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .mode-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.08);
        }

        .mode-btn.active[data-mode="all"] {
            background: #334155;
            color: #f8fafc;
        }

        .mode-btn.active[data-mode="yellow"] {
            background: #ca8a04;
            color: #ffffff;
            box-shadow: 0 0 10px rgba(234, 179, 8, 0.5);
        }

        .mode-btn.active[data-mode="orange"] {
            background: #ea580c;
            color: #ffffff;
            box-shadow: 0 0 10px rgba(234, 88, 12, 0.5);
        }

        .mode-btn.active[data-mode="red"] {
            background: #dc2626;
            color: #ffffff;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
        }

        .btn-action-small {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
            border: 1px solid var(--border-color);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
        }

        .btn-action-small:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        .btn-action-small.active {
            background: #0284c7;
            border-color: #38bdf8;
            box-shadow: 0 0 8px rgba(56, 189, 248, 0.4);
        }

        .osint-badge {
            display: inline-block;
            font-size: 9px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            margin-right: 4px;
            text-transform: uppercase;
        }

        .corridor-tooltip {
            background: rgba(15, 23, 42, 0.95) !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            color: #f8fafc !important;
            font-size: 11px !important;
            padding: 6px 10px !important;
            border-radius: 6px !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5) !important;
        }

        /* Reopen floating button */
        .reopen-panel-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 999;
            background: var(--panel-bg);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            color: #ffffff;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: none;
            align-items: center;
            gap: 6px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        }

        .reopen-panel-btn:hover {
            background: rgba(30, 41, 59, 0.95);
        }

        /* Side Panel - Draggable & Closable */
        .side-panel {
            position: absolute;
            top: 60px;
            right: 12px;
            width: 360px;
            max-height: calc(100vh - 80px);
            z-index: 1000;
            background: var(--panel-bg);
            backdrop-filter: blur(14px);
            border-radius: 12px;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: opacity 0.2s ease, transform 0.2s ease;
        }

        .panel-drag-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            background: rgba(0, 0, 0, 0.35);
            border-bottom: 1px solid var(--border-color);
            cursor: move;
            user-select: none;
        }

        .panel-drag-title {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .btn-panel-close {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 16px;
            cursor: pointer;
            padding: 0 4px;
            line-height: 1;
            transition: color 0.2s;
        }

        .btn-panel-close:hover {
            color: #ffffff;
        }

        .panel-tabs {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.2);
        }

        .panel-tab {
            flex: 1;
            padding: 8px 6px;
            text-align: center;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }

        .panel-tab.active {
            color: #ffffff;
            border-bottom-color: var(--accent-blue);
            background: rgba(255, 255, 255, 0.04);
        }

        .panel-content {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
        }

        .tab-pane {
            display: none;
        }

        .tab-pane.active {
            display: block;
        }

        /* Filter Section */
        .filter-section {
            margin-bottom: 14px;
        }

        .section-title {
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .category-filters {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }

        .filter-chip {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            padding: 5px 8px;
            border-radius: 6px;
            font-size: 11px;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 5px;
            cursor: pointer;
            transition: all 0.2s;
            user-select: none;
        }

        .filter-chip.active {
            background: rgba(59, 130, 246, 0.25);
            border-color: var(--accent-blue);
            color: #ffffff;
        }

        /* Leaderboard & Stats Cards */
        .stat-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 10px;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .stat-card:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.3);
            transform: translateX(-2px);
        }

        .district-info h4 {
            font-size: 12px;
            font-weight: 600;
            color: #f1f5f9;
        }

        .district-info p {
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .score-pill {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 700;
            white-space: nowrap;
        }

        /* Map Legend Overlay - Compact */
        .map-legend {
            position: absolute;
            bottom: 16px;
            left: 12px;
            z-index: 1000;
            background: var(--panel-bg);
            backdrop-filter: blur(10px);
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            font-size: 11px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .legend-color {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }

        /* Base Tile Switcher in Map (Google Roadmap & Google Satellite Only) */
        .tile-selector {
            position: absolute;
            bottom: 16px;
            right: 12px;
            z-index: 999;
            background: var(--panel-bg);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 3px;
            display: flex;
            gap: 3px;
        }

        .tile-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .tile-btn.active {
            background: var(--accent-blue);
            color: #ffffff;
        }

        /* Custom Popup Styling */
        .leaflet-popup-content-wrapper {
            background: #1e293b !important;
            color: #f8fafc !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.6) !important;
            padding: 2px !important;
        }

        .leaflet-popup-tip {
            background: #1e293b !important;
        }

        .popup-title {
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 2px;
            color: #ffffff;
        }

        .popup-cat {
            font-size: 10px;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
            color: var(--accent-blue);
            margin-bottom: 6px;
        }

        .popup-score-box {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(0, 0, 0, 0.35);
            padding: 5px 8px;
            border-radius: 6px;
            margin-bottom: 8px;
        }

        .popup-score-num {
            font-size: 16px;
            font-weight: 800;
        }

        .popup-desc {
            font-size: 11px;
            color: #cbd5e1;
            line-height: 1.35;
        }

        /* Time Series Modal Drawer */
        .analytics-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.75);
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
            border-radius: 14px;
            width: 90%;
            max-width: 800px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 20px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
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
            gap: 10px;
            margin-bottom: 20px;
        }

        .metric-card {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }

        .metric-val {
            font-size: 20px;
            font-weight: 800;
            color: #38bdf8;
            margin-bottom: 2px;
        }

        .metric-label {
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        /* Pulse Animation */
        @keyframes pulse-red {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        @keyframes pulse-orange {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(249, 115, 22, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(249, 115, 22, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(249, 115, 22, 0); }
        }
        @keyframes pulse-yellow {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(234, 179, 8, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0); }
        }
        .pulse-marker-red {
            animation: pulse-red 2s infinite;
            border-radius: 50%;
        }
        .pulse-marker-orange {
            animation: pulse-orange 2s infinite;
            border-radius: 50%;
        }
        .pulse-marker-yellow {
            animation: pulse-yellow 2s infinite;
            border-radius: 50%;
        }
        @keyframes corridorFlow {
            from { stroke-dashoffset: 32; }
            to { stroke-dashoffset: 0; }
        }
        .corridor-flow {
            animation: corridorFlow 2.5s linear infinite;
        }
    </style>
</head>
<body>

    <!-- Map Container -->
    <div id="map"></div>

    <!-- Top Navigation Bar - Draggable & Compact -->
    <div class="top-navbar" id="topNavbar">
        <div class="title-block">
            <div class="title-badge">Defense OSINT</div>
            <div class="title-text">
                <h1>Kyiv Defense Map</h1>
            </div>
        </div>

        <!-- Threat Mode Switcher -->
        <div class="threat-modes">
            <button class="mode-btn active" data-mode="all" onclick="setThreatMode('all')">
                <i class="fa-solid fa-layer-group"></i> Всі загрози
            </button>
            <button class="mode-btn" data-mode="yellow" onclick="setThreatMode('yellow')">
                <i class="fa-solid fa-triangle-exclamation"></i> Ударні БпЛА (Shahed)
            </button>
            <button class="mode-btn" data-mode="red" onclick="setThreatMode('red')" title="Ракети (Крилаті / Балістика)">
                <i class="fa-solid fa-radiation"></i> Ракети
            </button>
        </div>

        <!-- Time Range Selector (7 days default) -->
        <div class="time-range-modes">
            <button class="time-btn active" data-range="7d" onclick="setTimeRange('7d')" title="Показати удари за останні 7 днів">
                <i class="fa-solid fa-clock-rotate-left"></i> 7 днів
            </button>
            <button class="time-btn" data-range="30d" onclick="setTimeRange('30d')" title="Показати удари за 30 днів">
                30 днів
            </button>
            <button class="time-btn" data-range="all" onclick="setTimeRange('all')" title="Показати всі зафіксовані удари">
                Всі (6 міс)
            </button>
        </div>

        <button class="btn-action-small active" id="toggleCorridorsBtn" onclick="toggleCorridors()" title="Показати/приховати вектори підльоту БпЛА">
            <i class="fa-solid fa-route"></i> Вектори підльоту
        </button>

        <button class="btn-action-small" onclick="openNotebookLMModal()" style="background:linear-gradient(135deg, #1e3a8a, #4338ca); border-color:#6366f1;" title="Відкрити аналітичне зведення NotebookLM">
            <i class="fa-solid fa-book-bookmark"></i> NotebookLM OSINT
        </button>

        <button class="btn-action-small" onclick="openAnalyticsModal()">
            <i class="fa-solid fa-chart-line"></i> Time Series
        </button>
    </div>

    <!-- Reopen Floating Button (when panel is closed) -->
    <button id="openSidePanelBtn" class="reopen-panel-btn" onclick="openSidePanel()">
        <i class="fa-solid fa-chart-pie"></i> Панель розвідки
    </button>

    <!-- Side Intelligence Panel - Draggable & Closable -->
    <div class="side-panel" id="sidePanel">
        <div class="panel-drag-header" id="panelDragHeader">
            <div class="panel-drag-title">
                <i class="fa-solid fa-grip-lines"></i> Оборонна панель
            </div>
            <button class="btn-panel-close" onclick="closeSidePanel()" title="Закрити панель">&times;</button>
        </div>

        <div class="panel-tabs">
            <div class="panel-tab active" onclick="switchPanelTab('tab-districts')">Райони (10)</div>
            <div class="panel-tab" onclick="switchPanelTab('tab-objects')">Об'єкти & ППО</div>
            <div class="panel-tab" onclick="switchPanelTab('tab-incidents')">Хроніка ударів</div>
            <div class="panel-tab" onclick="switchPanelTab('tab-notebooklm')">OSINT Зведення</div>
        </div>

        <div class="panel-content">
            <!-- Tab 1: District Rankings -->
            <div id="tab-districts" class="tab-pane active">
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-shield-halved"></i> Рейтинг загрози районів Києва</div>
                    <p style="font-size:10px; color:var(--text-muted); margin-bottom:8px;">
                        Враховує щільність ударів, критичні об'єкти та оборонний периметр. Клікніть на район для фокусу.
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
                    <div class="category-filters" style="grid-template-columns: 1fr 1fr; gap: 5px;">
                        <div class="filter-chip active" data-cat="energy" onclick="toggleCategoryFilter('energy')">
                            <i class="fa-solid fa-bolt" style="color:#eab308"></i> Енергетика
                        </div>
                        <div class="filter-chip active" data-cat="transport" onclick="toggleCategoryFilter('transport')">
                            <i class="fa-solid fa-bridge" style="color:#38bdf8"></i> Мости / Транспорт
                        </div>
                        <div class="filter-chip active" data-cat="admin" onclick="toggleCategoryFilter('admin')">
                            <i class="fa-solid fa-landmark" style="color:#a855f7"></i> Влада / Зв'язок
                        </div>
                        <div class="filter-chip active" data-cat="industry" onclick="toggleCategoryFilter('industry')">
                            <i class="fa-solid fa-industry" style="color:#f43f5e"></i> ВПК / Промисловість
                        </div>
                        <div class="filter-chip active" data-cat="defense" onclick="toggleCategoryFilter('defense')" style="grid-column: span 2;">
                            <i class="fa-solid fa-shield-halved" style="color:#10b981"></i> Ешелони ППО & Турелі
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
                    <div class="section-title" id="incidents-tab-title"><i class="fa-solid fa-fire"></i> Зафіксовані удари (7 днів)</div>
                    <div id="incidents-list">
                        <!-- Rendered by JS -->
                    </div>
                </div>
            </div>

            <!-- Tab 4: NotebookLM OSINT Summary -->
            <div id="tab-notebooklm" class="tab-pane">
                <div class="filter-section">
                    <div class="section-title"><i class="fa-solid fa-brain"></i> Аналітичні висновки (6 місяців атак)</div>
                    <div style="font-size:11px; line-height:1.45; color:#cbd5e1; display:flex; flex-direction:column; gap:8px;">
                        <div style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color); border-radius:6px; padding:8px;">
                            <div style="color:#eab308; font-weight:700; margin-bottom:2px;"><i class="fa-solid fa-triangle-exclamation"></i> Ударні БпЛА (Shahed)</div>
                            Масоване комбіноване застосування ударних БпЛА вздовж річкових та транспортних коридорів підльоту столиці.
                        </div>
                        <div style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color); border-radius:6px; padding:8px;">
                            <div style="color:#10b981; font-weight:700; margin-bottom:2px;"><i class="fa-solid fa-crosshairs"></i> Розгортання турелей ППО</div>
                            Встановлення понад 12 автоматизованих турельних систем для протидії БпЛА на північному та західному рубежах.
                        </div>
                        <div style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color); border-radius:6px; padding:8px;">
                            <div style="color:#ef4444; font-weight:700; margin-bottom:2px;"><i class="fa-solid fa-meteor"></i> Балістичні залпи високої щільності</div>
                            Ударні серії балістики (до 40 ракет «Іскандер-М/С-400/Циркон» за 40 хв) по кластерах ВПК (Артем, Луч, Антонов).
                        </div>
                        <div style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color); border-radius:6px; padding:8px;">
                            <div style="color:#38bdf8; font-weight:700; margin-bottom:2px;"><i class="fa-solid fa-route"></i> Вектори прориву над водою</div>
                            Русло Дніпра (Оболонь — Вишгород) слугує ключовим нічним коридором для обходу стаціонарних радіолокаційних постів.
                        </div>
                        <button onclick="openNotebookLMModal()" style="background:#0284c7; color:#fff; border:none; border-radius:6px; padding:6px; font-size:11px; font-weight:600; cursor:pointer; margin-top:4px;">
                            <i class="fa-solid fa-file-lines"></i> Відкрити повний OSINT-документ
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Tile Layer Switcher: Google Roadmap & Google Satellite ONLY -->
    <div class="tile-selector">
        <button class="tile-btn active" data-tile="gmaps_road" onclick="setBaseTile('gmaps_road')">Google Maps</button>
        <button class="tile-btn" data-tile="gmaps_sat" onclick="setBaseTile('gmaps_sat')">Супутник</button>
    </div>

    <!-- Legend Overlay -->
    <div class="map-legend">
        <div style="font-weight:700; margin-bottom:2px; color:#cbd5e1;">Рівень небезпеки районів:</div>
        <div class="legend-item"><div class="legend-color" style="background:#dc2626;"></div> 75-100: Критичний ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#ea580c;"></div> 60-74: Високий ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#eab308;"></div> 45-59: Підвищений ризик</div>
        <div class="legend-item"><div class="legend-color" style="background:#10b981;"></div> 0-44: Помірний ризик</div>
        <div style="margin-top:4px; border-top:1px solid rgba(255,255,255,0.1); padding-top:4px; display:flex; flex-direction:column; gap:3px;">
            <div class="legend-item"><i class="fa-solid fa-circle" style="color:#eab308; font-size:9px;"></i> Ударний БпЛА (Shahed)</div>
            <div class="legend-item"><i class="fa-solid fa-circle" style="color:#ef4444; font-size:9px;"></i> Ракети (Крилаті / Балістика)</div>
            <div class="legend-item"><i class="fa-solid fa-shield-halved" style="color:#10b981; font-size:10px;"></i> Ешелон ППО & турелі</div>
            <div class="legend-item"><i class="fa-solid fa-route" style="color:#38bdf8; font-size:10px;"></i> Вектор підльоту БпЛА</div>
        </div>
    </div>

    <!-- NotebookLM OSINT Briefing Modal -->
    <div id="notebooklmModal" class="analytics-modal">
        <div class="modal-card" style="max-width:850px;">
            <div class="modal-header">
                <div>
                    <h2 style="font-size:18px; font-weight:700; display:flex; align-items:center; gap:8px;">
                        <i class="fa-solid fa-book-bookmark" style="color:#818cf8;"></i> NotebookLM Defense Intel Briefing
                    </h2>
                    <p style="font-size:11px; color:var(--text-muted);">
                        Хроніка повітряних атак по Києву за квітень — жовтень 2026 р. (6 місяців). Верифікація за зведеннями КМВА, ДСНС та OSINT.
                    </p>
                </div>
                <button class="btn-close" onclick="closeNotebookLMModal()">&times;</button>
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-val" style="color:#38bdf8;" id="modal-nblm-total">835</div>
                    <div class="metric-label">Верифікованих подій</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color:#eab308;" id="modal-nblm-shahed">745</div>
                    <div class="metric-label">Ударних БпЛА (Shahed)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color:#ef4444;" id="modal-nblm-missiles">89</div>
                    <div class="metric-label">Балістичних / крилатих ударів</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color:#10b981;" id="modal-nblm-turrets">3 сектори</div>
                    <div class="metric-label">Розгорнутих рубежів ППО</div>
                </div>
            </div>

            <div style="display:flex; flex-direction:column; gap:10px;">
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:12px;">
                    <h3 style="font-size:13px; font-weight:700; color:#eab308; margin-bottom:6px;">
                        <i class="fa-solid fa-triangle-exclamation"></i> 1. Тактика застосування ударних БпЛА (Shahed)
                    </h3>
                    <p style="font-size:12px; line-height:1.5; color:#cbd5e1;">
                        Противник застосовує комбіновані рої ударних БпЛА (Shahed) для виснаження оборони та ураження стратегічних переправ, енергетичної інфраструктури та логістичних вузлів столиці вздовж русла Дніпра та ключових магістралей.
                    </p>
                </div>

                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:12px;">
                    <h3 style="font-size:13px; font-weight:700; color:#10b981; margin-bottom:6px;">
                        <i class="fa-solid fa-shield-halved"></i> 2. Розгортання автоматизованих турельних рубежів ППО
                    </h3>
                    <p style="font-size:12px; line-height:1.5; color:#cbd5e1;">
                        Для парирування швидкісних реактивних цілей на річкових коридорах (русло Дніпра, Оболонь — Вишгород) та західних підходах (Святошин — Житомирська траса) столицю насичено автоматичними зенітними турелями та мобільними вогневими групами із тепловізійним автосупроводом (-35% до локального ризику).
                    </p>
                </div>

                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:12px;">
                    <h3 style="font-size:13px; font-weight:700; color:#ef4444; margin-bottom:6px;">
                        <i class="fa-solid fa-meteor"></i> 3. Концентровані балістичні залпи на виснаження перехоплювачів
                    </h3>
                    <p style="font-size:12px; line-height:1.5; color:#cbd5e1;">
                        Зафіксовано тактику залпового випуску балістичних ракет різних траєкторій (Іскандер-М, С-400, протикорабельні «Циркон» та північнокорейські KN-23) — до 40 цілей упродовж 40 хвилин. Основний фокус: авіабудівні та ракетні заводи (ДАХК «Артем», ДП «Луч», ДП «Антонов»).
                    </p>
                </div>

                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;">
                        <h3 style="font-size:13px; font-weight:700; color:#38bdf8; display:flex; align-items:center; gap:6px;">
                            <i class="fa-solid fa-database"></i> 4. Згенероване джерело даних для NotebookLM
                        </h3>
                        <button id="copyDigestBtn" onclick="copyNotebookLMDigest()" style="background:#0284c7; color:#fff; border:none; border-radius:5px; padding:4px 10px; font-size:11px; font-weight:600; cursor:pointer;">
                            <i class="fa-solid fa-copy"></i> Копіювати дайджест
                        </button>
                    </div>
                    <p style="font-size:11px; line-height:1.4; color:#94a3b8; margin-bottom:8px;">
                        🔐 <i>Google Auth Notice:</i> Оскільки спільне посилання на артефакт NotebookLM вимагає Google OAuth-авторизації, локальний конвеєр агрегував усі інциденти у файл <code style="color:#38bdf8;">data/raw/osint/kyiv_defense_intel_for_notebooklm.md</code>.
                    </p>
                    <pre id="digestPreview" style="background:#090d16; border:1px solid #1e293b; border-radius:6px; padding:8px 10px; font-size:10px; color:#cbd5e1; max-height:160px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; font-family:monospace;"></pre>
                </div>
            </div>
        </div>
    </div>

    <!-- Analytics Modal Drawer -->
    <div id="analyticsModal" class="analytics-modal">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 style="font-size:18px; font-weight:700;">Time Series Analysis & Валідація без Data Leakage</h2>
                    <p style="font-size:11px; color:var(--text-muted);">
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
                    <div class="metric-label">Brier Score</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" id="metric-alerts-cnt">99</div>
                    <div class="metric-label">Тривог проаналізовано</div>
                </div>
            </div>

            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:10px; padding:12px; margin-bottom:14px;">
                <h3 style="font-size:13px; font-weight:700; margin-bottom:6px; color:#38bdf8;">
                    <i class="fa-solid fa-shield-virus"></i> Методологія запобігання Data Leakage
                </h3>
                <p style="font-size:12px; line-height:1.45; color:#cbd5e1;">
                    Train split: дані до <b>1 вересня</b>. Test split: <b>1 вересня — 11 жовтня</b>.<br>
                    Усі ознаки моделі на момент $T$ обчислюються суворо з подій минулого. Жодного витоку майбутніх подій.
                </p>
            </div>

            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:10px; padding:12px;">
                <h3 style="font-size:13px; font-weight:700; margin-bottom:10px;">
                    <i class="fa-solid fa-clock"></i> Розподіл тривог за годинами доби
                </h3>
                <div style="display:flex; align-items:flex-end; gap:3px; height:100px; padding-top:10px;" id="hourly-chart">
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:10px; color:var(--text-muted);">
                    <span>00:00 (Нічний пік шахедів)</span>
                    <span>06:00</span>
                    <span>12:00</span>
                    <span>18:00</span>
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
        const DISTRICTS_GEOJSON = {{ districts_geojson_json }};
        const NOTEBOOKLM_DIGEST = {{ notebooklm_digest_json }};

        // State
        let currentThreatMode = 'all'; // 'all', 'yellow', 'orange', 'red'
        let currentTimeRange = '7d';   // Default to last 7 days!
        let activeCategories = new Set(['energy', 'transport', 'admin', 'industry', 'defense']);

        function getCutoffDate(rangeKey) {
            if (rangeKey === 'all') return null;
            let maxTs = 0;
            INCIDENTS_DATA.forEach(inc => {
                let parsed = Date.parse(inc.datetime.replace(' ', 'T'));
                if (!isNaN(parsed) && parsed > maxTs) maxTs = parsed;
            });
            if (maxTs === 0) maxTs = Date.now();

            if (rangeKey === '7d') {
                return maxTs - (7 * 24 * 60 * 60 * 1000);
            } else if (rangeKey === '30d') {
                return maxTs - (30 * 24 * 60 * 60 * 1000);
            }
            return null;
        }

        function setTimeRange(rangeKey) {
            currentTimeRange = rangeKey;
            document.querySelectorAll('.time-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.range === rangeKey);
            });
            renderIncidents();
            renderIncidentsList();
        }

        // Initialize Map
        const map = L.map('map', {
            center: [50.4501, 30.5234], // Kyiv Center
            zoom: 11,
            zoomControl: false
        });

        L.control.zoom({ position: 'bottomright' }).addTo(map);

        // Tile Layers (Google Maps & Satellite ONLY - Dark map removed)
        const tileLayers = {
            gmaps_road: L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
                maxZoom: 20,
                attribution: '© Google Maps'
            }),
            gmaps_sat: L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
                maxZoom: 20,
                attribution: '© Google Satellite'
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

        // Layer Groups
        let districtsLayerGroup = L.layerGroup().addTo(map);
        let corridorsLayerGroup = L.layerGroup().addTo(map);
        let objectsLayerGroup = L.layerGroup().addTo(map);
        let incidentsLayerGroup = L.layerGroup().addTo(map);

        // Inbound Attack Corridors (from OSINT Intel)
        const THREAT_CORRIDORS = [
            {
                id: "north_river",
                modes: ["all", "yellow"],
                name: "Північний річковий вектор (Вишгород — Оболонь — Дніпро)",
                coords: [[50.60, 30.48], [50.53, 30.50], [50.49, 30.53], [50.46, 30.54]],
                color: "#38bdf8",
                desc: "Нічний низьковисотний коридор прориву вздовж русла Дніпра для обходу РЛС."
            },
            {
                id: "west_zhytomyr",
                modes: ["all", "yellow", "red"],
                name: "Західний сектор (Макарів — Житомирська траса — Святошин)",
                coords: [[50.47, 30.05], [50.45, 30.22], [50.45, 30.37], [50.45, 30.40]],
                color: "#f97316",
                desc: "Вектор підльоту ударних БпЛА (Shahed) та ракет на промислові й авіаційні кластери."
            },
            {
                id: "south_obukhiv",
                modes: ["all", "yellow", "red"],
                name: "Південний сектор (Обухів — Козин — Корчувате — Голосіїв)",
                coords: [[50.15, 30.65], [50.28, 30.58], [50.35, 30.56], [50.39, 30.54]],
                color: "#a855f7",
                desc: "Коридор підльоту з півдня до логістичних вузлів та мостів (ударні БпЛА / КР)."
            },
            {
                id: "se_boryspil",
                modes: ["all", "yellow", "red"],
                name: "Південно-східний вектор (Бориспіль — Бортничі — Дарниця)",
                coords: [[50.35, 30.95], [50.37, 30.75], [50.40, 30.65], [50.42, 30.60]],
                color: "#ef4444",
                desc: "Східний ешелон підльоту через Бориспіль до ТЕЦ-4 та залізничних вузлів Лівого берега."
            },
            {
                id: "ne_brovary",
                modes: ["all", "yellow"],
                name: "Північно-східний вектор (Чернігівський напрямок — Бровари — Деснянський)",
                coords: [[50.58, 30.90], [50.53, 30.78], [50.50, 30.65], [50.50, 30.58]],
                color: "#eab308",
                desc: "Вектор підльоту роїв БпЛА з північного сходу на ТЕЦ-6 та лівобережні підстанції."
            }
        ];

        let corridorsVisible = true;

        function renderCorridors() {
            corridorsLayerGroup.clearLayers();
            if (!corridorsVisible) return;

            const modeNamesUA = {
                'all': 'Всі загрози',
                'yellow': 'Ударні БпЛА (Shahed)',
                'red': 'Ракети'
            };

            THREAT_CORRIDORS.forEach(c => {
                const isRelevant = c.modes.includes(currentThreatMode);
                const opacity = isRelevant ? 0.95 : 0.25;
                const weight = isRelevant ? 4 : 2;

                const polyline = L.polyline(c.coords, {
                    color: c.color,
                    weight: weight,
                    opacity: opacity,
                    dashArray: isRelevant ? '8, 8' : '4, 8',
                    className: isRelevant ? 'corridor-flow' : ''
                });
                const modesLabel = c.modes.map(m => modeNamesUA[m] || m).join(', ');
                polyline.bindTooltip(`<b>${c.name}</b><br>${c.desc}<br><small style="color:${c.color};">Релевантні загрози: ${modesLabel}</small>`, {
                    className: 'corridor-tooltip',
                    sticky: true
                });
                corridorsLayerGroup.addLayer(polyline);

                const endPoint = c.coords[c.coords.length - 1];
                const arrowMarker = L.circleMarker(endPoint, {
                    radius: isRelevant ? 6 : 4,
                    fillColor: c.color,
                    color: '#fff',
                    weight: isRelevant ? 2 : 1,
                    fillOpacity: opacity
                });
                corridorsLayerGroup.addLayer(arrowMarker);
            });
        }

        function toggleCorridors() {
            corridorsVisible = !corridorsVisible;
            const btn = document.getElementById('toggleCorridorsBtn');
            if (btn) btn.classList.toggle('active', corridorsVisible);
            renderCorridors();
        }

        function getScoreColor(score) {
            if (score >= 75) return '#dc2626'; // Red / Critical
            if (score >= 60) return '#ea580c'; // Orange / High
            if (score >= 45) return '#eab308'; // Yellow / Moderate-High
            return '#10b981'; // Green / Moderate
        }

        function getCategoryIcon(cat) {
            switch(cat) {
                case 'energy': return 'fa-bolt';
                case 'transport': return 'fa-bridge';
                case 'admin': return 'fa-landmark';
                case 'industry': return 'fa-industry';
                case 'defense': return 'fa-shield-halved';
                default: return 'fa-location-dot';
            }
        }

        // 1. Render All 10 Kyiv Districts Polygons (Dynamically reacting to active threat mode)
        function renderDistrictsPolygons() {
            districtsLayerGroup.clearLayers();

            const districtStatsMap = {};
            RISK_DATA.districts.forEach(d => {
                districtStatsMap[d.district] = d;
            });

            const modeKey = (currentThreatMode === 'all') ? 'all' : currentThreatMode;

            L.geoJSON(DISTRICTS_GEOJSON, {
                style: function(feature) {
                    const dName = feature.properties.district;
                    const stats = districtStatsMap[dName] || {};
                    const exposure = (stats.exposure_by_mode && stats.exposure_by_mode[modeKey] !== undefined)
                        ? stats.exposure_by_mode[modeKey]
                        : (stats.exposure_index || 50);
                    const col = getScoreColor(exposure);
                    return {
                        fillColor: col,
                        fillOpacity: 0.22,
                        weight: 2,
                        color: col,
                        dashArray: '4, 4'
                    };
                },
                onEachFeature: function(feature, layer) {
                    const dName = feature.properties.district;
                    const stats = districtStatsMap[dName] || {};
                    const exposure = (stats.exposure_by_mode && stats.exposure_by_mode[modeKey] !== undefined)
                        ? stats.exposure_by_mode[modeKey]
                        : (stats.exposure_index || 50);
                    const safety = (stats.safety_by_mode && stats.safety_by_mode[modeKey] !== undefined)
                        ? stats.safety_by_mode[modeKey]
                        : (stats.safety_score || 50);
                    const rank = (stats.rank_by_mode && stats.rank_by_mode[modeKey] !== undefined)
                        ? stats.rank_by_mode[modeKey]
                        : (stats.threat_rank || '-');
                    const status = (stats.status_by_mode && stats.status_by_mode[modeKey] !== undefined)
                        ? stats.status_by_mode[modeKey]
                        : (stats.status || '');
                    const incidents = (stats.incidents_by_mode && stats.incidents_by_mode[modeKey] !== undefined)
                        ? stats.incidents_by_mode[modeKey]
                        : (stats.incidents_count || 0);
                    const col = getScoreColor(exposure);

                    layer.on('mouseover', function(e) {
                        layer.setStyle({
                            fillOpacity: 0.42,
                            weight: 3,
                            dashArray: ''
                        });
                    });

                    layer.on('mouseout', function(e) {
                        layer.setStyle({
                            fillOpacity: 0.22,
                            weight: 2,
                            dashArray: '4, 4'
                        });
                    });

                    const modeLabel = (currentThreatMode === 'yellow') ? 'Ударні БпЛА (Shahed)' :
                                      (currentThreatMode === 'red') ? 'Ракети (Крилаті / Балістика)' : 'Всі загрози';

                    const popup = `
                        <div class="popup-title">${dName} район</div>
                        <div class="popup-cat">Режим: <b>${modeLabel}</b> • Ранг загрози: #${rank}</div>
                        <div class="popup-score-box">
                            <span style="font-size:11px; color:#cbd5e1;">Індекс небезпеки:</span>
                            <span class="popup-score-num" style="color:${col};">${exposure}/100</span>
                        </div>
                        <div style="font-size:11px; margin-bottom:4px;">
                            Статус: <b style="color:${col};">${status}</b><br>
                            Запас безпеки: <b>${safety}%</b><br>
                            Ударів/уламків у режимі: <b>${incidents}</b>
                        </div>
                        <div class="popup-desc">${feature.properties.description || ''}</div>
                    `;
                    layer.bindPopup(popup);
                }
            }).addTo(districtsLayerGroup);
        }

        // 2. Render Infrastructure Objects
        function renderObjects() {
            objectsLayerGroup.clearLayers();

            RISK_DATA.objects.forEach(obj => {
                if (!activeCategories.has(obj.category)) return;

                const isDefense = obj.category === 'defense';
                const scoreObj = obj.scores[currentThreatMode] || obj.scores['all'];
                const score = scoreObj.score;
                const tier = scoreObj.tier;
                const color = isDefense ? '#10b981' : getScoreColor(score);

                if (isDefense) {
                    const defenseCircle = L.circle([obj.lat, obj.lon], {
                        radius: 3500,
                        color: '#10b981',
                        weight: 1.5,
                        dashArray: '6, 6',
                        fillColor: '#10b981',
                        fillOpacity: 0.08,
                        interactive: false
                    });
                    objectsLayerGroup.addLayer(defenseCircle);
                }

                const iconHtml = `
                    <div style="background:${color}; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; border:2px solid white; box-shadow:0 3px 8px rgba(0,0,0,0.4);">
                        <i class="fa-solid ${getCategoryIcon(obj.category)}" style="font-size:11px;"></i>
                    </div>
                `;

                const pulseClass = isDefense ? '' : (
                    (currentThreatMode === 'red' && score >= 75) ? 'pulse-marker-red' :
                    (currentThreatMode === 'yellow' && score >= 75 ? 'pulse-marker-yellow' : '')
                );

                const customIcon = L.divIcon({
                    html: iconHtml,
                    className: pulseClass,
                    iconSize: [28, 28],
                    iconAnchor: [14, 14]
                });

                const marker = L.marker([obj.lat, obj.lon], { icon: customIcon });

                const scoreLabel = isDefense ? 'Індекс активності ППО:' : 'Індекс небезпеки:';
                const statusLabel = isDefense ?
                    `Статус: <b style="color:#10b981;">Активний сектор перехоплення</b>` :
                    `Статус: <b style="color:${color};">${tier}</b> | Близькість до уламків: +${scoreObj.proximity} б.`;

                const popupContent = `
                    <div class="popup-title">${obj.name}</div>
                    <div class="popup-cat"><i class="fa-solid ${getCategoryIcon(obj.category)}"></i> ${formatCategoryUA(obj.category)} • ${obj.district}</div>
                    <div class="popup-score-box">
                        <span style="font-size:11px; color:#cbd5e1;">${scoreLabel}</span>
                        <span class="popup-score-num" style="color:${color};">${score}/100</span>
                    </div>
                    <div style="font-size:10px; margin-bottom:6px; color:#94a3b8;">
                        ${statusLabel}
                    </div>
                    <div class="popup-desc">${obj.description}</div>
                `;

                marker.bindPopup(popupContent);
                objectsLayerGroup.addLayer(marker);
            });
        }

        function formatCategoryUA(cat) {
            switch(cat) {
                case 'energy': return 'Енергетика';
                case 'transport': return 'Мости / Транспорт';
                case 'admin': return 'Влада / Зв\'язок';
                case 'industry': return 'ВПК / Промисловість';
                case 'defense': return 'Ешелони ППО & Турелі';
                default: return 'Інфраструктура';
            }
        }

        function formatThreatTypeUA(type) {
            switch(type) {
                case 'drone_shahed':
                case 'drone_jet':
                    return 'Ударний БпЛА (Shahed)';
                case 'drone_decoy':
                    return 'Дрон-приманка';
                case 'missile_ballistic':
                    return 'Балістична ракета';
                case 'missile_cruise':
                    return 'Крилата ракета';
                default:
                    return 'Ударний БпЛА (Shahed)';
            }
        }

        function formatImpactTypeUA(type) {
            switch(type) {
                case 'debris_fall':
                    return 'Падіння уламків';
                case 'direct_hit':
                    return 'Пряме влучання';
                case 'fire':
                    return 'Локальна пожежа';
                case 'intercepted_airburst':
                    return 'Збиття в повітрі';
                default:
                    return 'Падіння уламків';
            }
        }

        // 3. Render Incidents (with 7-day default filter)
        function renderIncidents() {
            incidentsLayerGroup.clearLayers();
            const cutoff = getCutoffDate(currentTimeRange);
            let count = 0;

            INCIDENTS_DATA.forEach(inc => {
                if (currentThreatMode === 'yellow' && inc.alert_level !== 'yellow') return;
                if (currentThreatMode === 'red' && inc.alert_level !== 'red') return;

                if (cutoff) {
                    let parsed = Date.parse(inc.datetime.replace(' ', 'T'));
                    if (!isNaN(parsed) && parsed < cutoff) return;
                }
                count++;

                let incColor = '#eab308';
                if (inc.threat_type === 'missile_ballistic' || inc.alert_level === 'red') {
                    incColor = '#ef4444';
                } else if (inc.threat_type === 'missile_cruise') {
                    incColor = '#ec4899';
                }

                const incidentIcon = L.divIcon({
                    html: `<div style="background:${incColor}; width:13px; height:13px; border-radius:50%; border:2px solid #ffffff; box-shadow:0 0 6px ${incColor};"></div>`,
                    className: '',
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                });

                const threatUA = formatThreatTypeUA(inc.threat_type);
                const impactUA = formatImpactTypeUA(inc.impact_type);

                const marker = L.marker([inc.lat, inc.lon], { icon: incidentIcon });
                const popup = `
                    <div class="popup-title" style="margin-bottom:6px;"><i class="fa-solid fa-triangle-exclamation" style="color:${incColor}"></i> ${inc.district}</div>
                    <div style="font-size:11px; line-height:1.5; color:#cbd5e1;">
                        <div><b>Локація:</b> ${inc.district}, ${inc.location_hint}</div>
                        <div><b>Час:</b> ${inc.datetime}</div>
                        <div><b>Тип загрози:</b> ${threatUA}</div>
                        <div><b>Наслідки:</b> ${inc.description || impactUA}</div>
                        <div><b>Джерело:</b> ${inc.source}</div>
                    </div>
                `;
                marker.bindPopup(popup);
                incidentsLayerGroup.addLayer(marker);
            });

            const titleEl = document.getElementById('incidents-tab-title');
            if (titleEl) {
                const rangeLabel = currentTimeRange === '7d' ? 'за 7 днів' : (currentTimeRange === '30d' ? 'за 30 днів' : 'за весь час');
                titleEl.innerHTML = `<i class="fa-solid fa-fire"></i> Зафіксовані удари (${count} подій, ${rangeLabel})`;
            }
        }

        // Mode Toggler
        function setThreatMode(mode) {
            currentThreatMode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.mode === mode);
            });
            renderDistrictsPolygons();
            renderDistrictsList();
            renderObjects();
            renderIncidents();
            renderObjectsList();
            renderIncidentsList();
            renderCorridors();
        }

        // Category Filter
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

        // Tabs
        function switchPanelTab(tabId) {
            document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            event.currentTarget.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }

        // Panel Close / Open
        function closeSidePanel() {
            document.getElementById('sidePanel').style.display = 'none';
            document.getElementById('openSidePanelBtn').style.display = 'flex';
        }

        function openSidePanel() {
            document.getElementById('sidePanel').style.display = 'flex';
            document.getElementById('openSidePanelBtn').style.display = 'none';
        }

        function renderDistrictsList() {
            const container = document.getElementById('districts-list');
            container.innerHTML = '';
            const modeKey = (currentThreatMode === 'all') ? 'all' : currentThreatMode;

            // Sort districts by active mode exposure descending
            const sortedDistricts = [...RISK_DATA.districts].sort((a, b) => {
                const expA = (a.exposure_by_mode && a.exposure_by_mode[modeKey] !== undefined) ? a.exposure_by_mode[modeKey] : a.exposure_index;
                const expB = (b.exposure_by_mode && b.exposure_by_mode[modeKey] !== undefined) ? b.exposure_by_mode[modeKey] : b.exposure_index;
                return expB - expA;
            });

            sortedDistricts.forEach((d, idx) => {
                const exposure = (d.exposure_by_mode && d.exposure_by_mode[modeKey] !== undefined) ? d.exposure_by_mode[modeKey] : d.exposure_index;
                const rank = (d.rank_by_mode && d.rank_by_mode[modeKey] !== undefined) ? d.rank_by_mode[modeKey] : (idx + 1);
                const status = (d.status_by_mode && d.status_by_mode[modeKey] !== undefined) ? d.status_by_mode[modeKey] : d.status;
                const badgeColor = (d.badge_by_mode && d.badge_by_mode[modeKey] !== undefined) ? d.badge_by_mode[modeKey] : d.badge_color;
                const incCount = (d.incidents_by_mode && d.incidents_by_mode[modeKey] !== undefined) ? d.incidents_by_mode[modeKey] : d.incidents_count;

                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([d.center_lat, d.center_lon], 13);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>#${rank} ${d.district}</h4>
                        <p>${status} • Інцидентів: ${incCount}</p>
                    </div>
                    <div class="score-pill" style="background:${badgeColor}33; color:${badgeColor}; border:1px solid ${badgeColor};">
                        ${exposure} ризик
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
                const isDefense = obj.category === 'defense';
                const scoreObj = obj.scores[currentThreatMode] || obj.scores['all'];
                const score = scoreObj.score;
                const color = isDefense ? '#10b981' : getScoreColor(score);
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([obj.lat, obj.lon], 15);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>${obj.name}</h4>
                        <p>${obj.district} • ${formatCategoryUA(obj.category)}</p>
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
            const cutoff = getCutoffDate(currentTimeRange);
            let displayCount = 0;

            INCIDENTS_DATA.forEach(inc => {
                if (currentThreatMode === 'yellow' && inc.alert_level !== 'yellow') return;
                if (currentThreatMode === 'red' && inc.alert_level !== 'red') return;

                if (cutoff) {
                    let parsed = Date.parse(inc.datetime.replace(' ', 'T'));
                    if (!isNaN(parsed) && parsed < cutoff) return;
                }
                displayCount++;
                if (displayCount > 60) return; // keep side list responsive

                let badgeColor = '#eab308';
                let badgeBg = '#eab30822';
                if (inc.alert_level === 'red') {
                    badgeColor = '#ef4444';
                    badgeBg = '#ef444422';
                }

                const card = document.createElement('div');
                card.className = 'stat-card';
                card.onclick = () => map.flyTo([inc.lat, inc.lon], 15);
                card.innerHTML = `
                    <div class="district-info">
                        <h4>${inc.district}</h4>
                        <p>${inc.datetime.split(' ')[0]} • ${inc.location_hint}</p>
                    </div>
                    <span style="font-size:10px; padding:2px 6px; border-radius:4px; background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeColor}44; font-weight:600;">
                        ${formatThreatTypeUA(inc.threat_type)}
                    </span>
                `;
                container.appendChild(card);
            });

            if (displayCount === 0) {
                container.innerHTML = '<div style="font-size:11px; color:#94a3b8; padding:10px; text-align:center;">За обраний період подій не зафіксовано.</div>';
            }
        }

        function updateModalMetrics() {
            const summary = RISK_DATA.incidents_summary || {};
            const byThreat = summary.by_threat || {};
            const total = summary.total || INCIDENTS_DATA.length;
            const shahed = (byThreat.drone_shahed || 0) + (byThreat.drone_jet || 0);
            const missiles = (byThreat.missile_ballistic || 0) + (byThreat.missile_cruise || 0);
            const turrets = RISK_DATA.objects.filter(o => o.category === 'defense').length;

            const elTotal = document.getElementById('modal-nblm-total');
            if (elTotal) elTotal.innerText = total;
            const elShahed = document.getElementById('modal-nblm-shahed');
            if (elShahed) elShahed.innerText = shahed;
            const elJet = document.getElementById('modal-nblm-jet');
            if (elJet) elJet.innerText = shahed;
            const elMissiles = document.getElementById('modal-nblm-missiles');
            if (elMissiles) elMissiles.innerText = missiles;
            const elTurrets = document.getElementById('modal-nblm-turrets');
            if (elTurrets) elTurrets.innerText = turrets + ' сектори';

            const previewEl = document.getElementById('digestPreview');
            if (previewEl && NOTEBOOKLM_DIGEST) {
                previewEl.innerText = NOTEBOOKLM_DIGEST;
            }
        }

        function copyNotebookLMDigest() {
            if (navigator.clipboard && NOTEBOOKLM_DIGEST) {
                navigator.clipboard.writeText(NOTEBOOKLM_DIGEST).then(() => {
                    const btn = document.getElementById('copyDigestBtn');
                    if (btn) {
                        const orig = btn.innerHTML;
                        btn.innerHTML = '<i class="fa-solid fa-check"></i> Скопійовано!';
                        btn.style.background = '#10b981';
                        setTimeout(() => {
                            btn.innerHTML = orig;
                            btn.style.background = '#0284c7';
                        }, 2000);
                    }
                }).catch(() => {
                    alert('Дайджест готовий у data/raw/osint/kyiv_defense_intel_for_notebooklm.md');
                });
            }
        }

        // NotebookLM OSINT Modal
        function openNotebookLMModal() {
            updateModalMetrics();
            document.getElementById('notebooklmModal').classList.add('open');
        }

        function closeNotebookLMModal() {
            document.getElementById('notebooklmModal').classList.remove('open');
        }

        // Analytics Modal
        function openAnalyticsModal() {
            document.getElementById('analyticsModal').classList.add('open');
            if (TS_EVAL && TS_EVAL.metrics) {
                const elRoc = document.getElementById('metric-roc-auc');
                if (elRoc) elRoc.innerText = TS_EVAL.metrics.model_roc_auc;
                const elBase = document.getElementById('metric-baseline-auc');
                if (elBase) elBase.innerText = TS_EVAL.metrics.baseline_roc_auc;
                const elBrier = document.getElementById('metric-brier');
                if (elBrier) elBrier.innerText = TS_EVAL.metrics.model_brier_score;
            }
            if (TS_STATS && TS_STATS.total_alerts) {
                const elCnt = document.getElementById('metric-alerts-cnt');
                if (elCnt) elCnt.innerText = TS_STATS.total_alerts;
            }
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
                bar.style.borderRadius = '2px 2px 0 0';
                bar.title = `${hour}:00 - ${val} тривог`;
                chart.appendChild(bar);
            });
        }

        // Generic Draggable Helper
        function makeDraggable(element, handle) {
            let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
            handle.onmousedown = dragMouseDown;

            function dragMouseDown(e) {
                if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
                e.preventDefault();
                pos3 = e.clientX;
                pos4 = e.clientY;
                document.onmouseup = closeDragElement;
                document.onmousemove = elementDrag;
            }

            function elementDrag(e) {
                e.preventDefault();
                pos1 = pos3 - e.clientX;
                pos2 = pos4 - e.clientY;
                pos3 = e.clientX;
                pos4 = e.clientY;
                element.style.top = (element.offsetTop - pos2) + "px";
                element.style.left = (element.offsetLeft - pos1) + "px";
                element.style.right = 'auto';
                element.style.bottom = 'auto';
            }

            function closeDragElement() {
                document.onmouseup = null;
                document.onmousemove = null;
            }
        }

        // Initialize Dragging on Panels
        makeDraggable(document.getElementById('sidePanel'), document.getElementById('panelDragHeader'));
        makeDraggable(document.getElementById('topNavbar'), document.getElementById('topNavbar'));

        // Initial Boot
        renderDistrictsPolygons();
        renderCorridors();
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
    incidents_df = risk_engine.incidents_df
    incidents_list = incidents_df.to_dict(orient="records")

    # 4. Load districts geojson
    districts_geojson_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "curated"
        / "kyiv_districts.geojson"
    )
    with open(districts_geojson_path, "r", encoding="utf-8") as f:
        districts_geojson = json.load(f)

    # 5. Load NotebookLM digest text
    nblm_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "raw"
        / "osint"
        / "kyiv_defense_intel_for_notebooklm.md"
    )
    nblm_text = ""
    if nblm_path.exists():
        with open(nblm_path, "r", encoding="utf-8") as f:
            nblm_text = f.read()

    # 6. Render Jinja template
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        risk_data_json=json.dumps(risk_data, ensure_ascii=False),
        ts_stats_json=json.dumps(ts_stats, ensure_ascii=False),
        ts_eval_json=json.dumps(ts_eval, ensure_ascii=False),
        incidents_json=json.dumps(incidents_list, ensure_ascii=False),
        districts_geojson_json=json.dumps(districts_geojson, ensure_ascii=False),
        notebooklm_digest_json=json.dumps(nblm_text, ensure_ascii=False),
    )

    out_file = Path(__file__).resolve().parent.parent / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Interactive Dashboard successfully built at: {out_file}")
    return out_file


if __name__ == "__main__":
    build_dashboard()
