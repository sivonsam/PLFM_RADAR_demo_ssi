# Athene Local Demo Dashboard

Browser-based Maritime Situational Awareness demo — runs entirely on your laptop.

## Quick start

```bash
# From repo root
pip3 install fastapi uvicorn

cd athene/services/dashboard
uvicorn app:app --port 8765
```

Then open **http://localhost:8765** in your browser.

## What you see

| Layer | Source |
|-------|--------|
| Radar tracks (14 vessels) | Athene simulator — Gulf of Finland |
| Live AIS vessels (~800) | Digitraffic / Traficom (open, no key) |
| Weather strip | FMI open data (Helsinki obs) |
| Nautical chart overlay | OpenSeaMap (free tiles) |
| Bathymetry | EMODnet WMS (EU open data) |

## Vessel archetypes

| Type | Count | Track type | AIS |
|------|-------|-----------|-----|
| Helsinki–Tallinn ferry | 2 | confirmed | ✅ |
| Cargo (east↔west) | 4 | confirmed | ✅ |
| Small craft (archipelago) | 6 | confirmed / unknown | ~65% |
| Patrol vessel | 1 | confirmed | ✅ |
| **Dark target** | **1** | **dark** | ❌ |

After ~2 minutes, the dark target triggers an **alert** in the sidebar (no AIS signal detected).

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ATHENE_RATE` | `1.0` | Radar events per second |
| `ATHENE_DT` | `5.0` | Simulated time-step (seconds per tick) |
| `ATHENE_LIVE_AIS` | `1` | `1` = fetch live Digitraffic AIS; `0` = offline |

## Offline mode (no internet)

```bash
ATHENE_LIVE_AIS=0 uvicorn app:app --port 8765
```

Simulator tracks still work; AIS and weather will show `—`.

## Next steps (when Azure/ESRI provisioned)

The same event schema (`schema.py`, `event_id` UUID) flows unchanged into:
- Azure Event Hub → Eventhouse → OneLake → ArcGIS Online
