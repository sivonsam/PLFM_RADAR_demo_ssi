"""
Digitraffic AIS live vessel feed for Athene demo.

Polls the Digitraffic Marine REST API (Finnish Transport Infrastructure Agency)
for the latest vessel positions in the Gulf of Finland area.  No API key is
required.  Results are cached for POLL_INTERVAL seconds.

AIS data is used in two ways by the simulator:
  correlated — a synthetic radar track is matched to a real AIS vessel (MMSI join)
  standalone — AIS vessels visible to the feed but not yet in the radar pool

On any network failure the module returns the stale cache silently so the
simulator continues running without AIS data rather than crashing.

Digitraffic open data terms: https://www.digitraffic.fi/en/terms-of-service/
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from dataclasses import dataclass

_AIS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"

# Bounding box for Gulf of Finland demo area
_LAT_MIN, _LAT_MAX = 59.30, 60.50
_LON_MIN, _LON_MAX = 22.50, 27.50

POLL_INTERVAL  = 30   # seconds between Digitraffic API polls
FETCH_TIMEOUT  = 8    # seconds


@dataclass
class AISVessel:
    mmsi: int
    lat: float
    lon: float
    speed_mps: float     # converted from SOG (knots)
    heading_deg: float
    cog: float           # Course over ground (degrees)
    name: str | None = None
    vessel_type_code: int | None = None  # AIS ship type (ITU-R M.1371)


def _knots_to_mps(knots: float) -> float:
    return round(knots * 0.51444, 2)


_cache: dict[int, AISVessel] = {}
_last_fetch: float = 0.0


def fetch_ais() -> dict[int, AISVessel]:
    """
    Return a dict of MMSI → AISVessel for vessels in the Gulf of Finland area.
    Refreshed at most every POLL_INTERVAL seconds.
    """
    global _last_fetch
    now = time.monotonic()
    if _cache and (now - _last_fetch) < POLL_INTERVAL:
        return _cache

    try:
        req = urllib.request.Request(_AIS_URL, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw)

        _cache.clear()
        for feature in data.get("features", []):
            props  = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None])
            if coords[0] is None or coords[1] is None:
                continue
            lon_v, lat_v = float(coords[0]), float(coords[1])
            if not (_LAT_MIN <= lat_v <= _LAT_MAX and _LON_MIN <= lon_v <= _LON_MAX):
                continue
            mmsi = props.get("mmsi")
            if not mmsi:
                continue
            sog = float(props.get("sog") or 0.0)
            hdg = float(props.get("heading") or props.get("cog") or 0.0)
            cog = float(props.get("cog") or 0.0)
            _cache[mmsi] = AISVessel(
                mmsi=mmsi,
                lat=round(lat_v, 6),
                lon=round(lon_v, 6),
                speed_mps=_knots_to_mps(sog),
                heading_deg=round(hdg % 360, 1),
                cog=round(cog % 360, 1),
                vessel_type_code=props.get("shipType"),
            )
        _last_fetch = now

    except Exception:  # noqa: BLE001
        _last_fetch = now

    return _cache
