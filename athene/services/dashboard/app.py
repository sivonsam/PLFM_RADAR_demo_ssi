"""
Athene local demo dashboard — FastAPI backend

Endpoints
---------
GET /               Serves the map UI (static/index.html)
GET /stream         Server-Sent Events: radar track events from Athene simulator
GET /api/ais        Latest AIS vessels from Digitraffic (Gulf of Finland bbox)
GET /api/weather    Latest FMI weather snapshot for Helsinki
GET /api/status     Session info, track counts, dark-target alert list

Run
---
  cd athene/services/dashboard
  uvicorn app:app --reload --port 8765

Then open http://localhost:8765 in your browser.

Flags (environment variables)
------------------------------
  ATHENE_RATE     Simulator events per second  (default 1.0)
  ATHENE_DT       Simulated time-step seconds  (default 5.0)
  ATHENE_LIVE_AIS 1 = correlate with live Digitraffic AIS (default 1)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Allow imports from sibling simulator package
sys.path.insert(0, str(Path(__file__).parent.parent / "simulator"))

from ais_feed import fetch_ais
from archetypes import initial_pool, respawn
from schema import Meta, RadarEvent, SeaState, TargetFields
from weather import WeatherSnapshot, fetch_weather

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── Config ────────────────────────────────────────────────────────────────────

RATE     = float(os.environ.get("ATHENE_RATE",     "1.0"))
DT       = float(os.environ.get("ATHENE_DT",       "5.0"))
LIVE_AIS = os.environ.get("ATHENE_LIVE_AIS", "1") == "1"

DARK_ALERT_SECS = 120   # flag dark target after this many seconds with no AIS

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Athene Demo")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# ── Shared state ──────────────────────────────────────────────────────────────

_session_id   = RadarEvent.make_id()
_pool         = initial_pool()
_event_count  = 0
_dark_first_seen: dict[str, float] = {}   # target_id → monotonic time first seen
_dark_alerts:    list[dict]        = []   # raised alerts for the UI


def _sea_state(snap: WeatherSnapshot) -> SeaState | None:
    if snap.wind_speed_mps is None:
        return None
    return SeaState(
        wave_height_m=snap.wave_height_m,
        wind_speed_mps=snap.wind_speed_mps,
        wind_dir_deg=snap.wind_dir_deg,
        station_id=snap.station_id,
    )


def _build_event(track, sea, ais_vessels: dict) -> RadarEvent:
    correlated = track.mmsi is not None and track.mmsi in ais_vessels
    live_cog   = ais_vessels[track.mmsi].cog if correlated else None
    return RadarEvent(
        event_id=RadarEvent.make_id(),
        event_type="radar_track",
        source="athene_sim+ais" if correlated else "athene_sim",
        timestamp_utc=RadarEvent.now_utc(),
        session_id=_session_id,
        target=TargetFields(
            target_id=track.target_id,
            track_type=track.track_type,
            vessel_type=track.vessel_type,
            lat=track.lat,
            lon=track.lon,
            speed_mps=track.speed_mps,
            heading_deg=round(track.heading_deg, 1),
            confidence=track.confidence,
            mmsi=track.mmsi,
            vessel_name=track.vessel_name,
            cog=live_cog,
        ),
        sea_state=sea,
        meta=Meta(correlated=correlated, scenario=track.scenario),
    )


def _check_dark_alert(event: RadarEvent) -> None:
    """Raise an alert if a dark target has persisted > DARK_ALERT_SECS."""
    t = event.target
    if t.track_type != "dark":
        return
    now = time.monotonic()
    tid = t.target_id
    if tid not in _dark_first_seen:
        _dark_first_seen[tid] = now
        return
    age = now - _dark_first_seen[tid]
    if age >= DARK_ALERT_SECS and not any(a["target_id"] == tid for a in _dark_alerts):
        _dark_alerts.append({
            "target_id":    tid,
            "lat":          t.lat,
            "lon":          t.lon,
            "age_s":        round(age),
            "alert_time":   RadarEvent.now_utc(),
            "message":      f"DARK TARGET: no AIS signal for {round(age)}s — track {tid[:8]}",
        })


# ── SSE stream ────────────────────────────────────────────────────────────────

async def _event_generator():
    global _event_count
    interval = 1.0 / max(RATE, 0.001)
    while True:
        weather  = fetch_weather()
        ais      = fetch_ais() if LIVE_AIS else {}
        sea      = _sea_state(weather)

        for idx, track in enumerate(_pool):
            track.step(DT)
            if track.out_of_bounds():
                _pool[idx] = respawn(track)
                track = _pool[idx]

            event = _build_event(track, sea, ais)
            _check_dark_alert(event)
            _event_count += 1

            payload = json.dumps(event.to_dict())
            yield f"data: {payload}\n\n"
            await asyncio.sleep(interval)


@app.get("/stream")
async def stream():
    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Data API ──────────────────────────────────────────────────────────────────

@app.get("/api/ais")
def api_ais():
    vessels = fetch_ais()
    return JSONResponse([
        {
            "mmsi":             v.mmsi,
            "lat":              v.lat,
            "lon":              v.lon,
            "speed_mps":        v.speed_mps,
            "heading_deg":      v.heading_deg,
            "cog":              v.cog,
            "vessel_type_code": v.vessel_type_code,
        }
        for v in vessels.values()
    ])


@app.get("/api/weather")
def api_weather():
    snap = fetch_weather()
    return JSONResponse({
        "wind_speed_mps": snap.wind_speed_mps,
        "wind_dir_deg":   snap.wind_dir_deg,
        "wave_height_m":  snap.wave_height_m,
        "station_id":     snap.station_id,
    })


@app.get("/api/status")
def api_status():
    dark_active = [
        tid for tid, t in _dark_first_seen.items()
        if (time.monotonic() - t) < 600
    ]
    return JSONResponse({
        "session_id":    _session_id,
        "event_count":   _event_count,
        "track_count":   len(_pool),
        "dark_active":   len(dark_active),
        "dark_alerts":   _dark_alerts[-10:],
        "live_ais":      LIVE_AIS,
        "rate_hz":       RATE,
    })


# ── Static / index ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
