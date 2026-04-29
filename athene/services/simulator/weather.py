"""
FMI (Finnish Meteorological Institute) weather context for Athene demo.

Fetches the latest surface observations near Helsinki via the FMI open WFS API
(no API key required) and attaches sea-state context to simulator events.

Results are cached for CACHE_TTL seconds so the API is not hammered every tick.
On any network or parse failure the module returns a null snapshot silently —
the simulator continues without weather context rather than crashing.

Wave height is estimated from wind speed using a simplified Beaufort proxy
calibrated for the enclosed Gulf of Finland fetch.

FMI open data terms: https://en.ilmatieteenlaitos.fi/open-data-manual
"""
from __future__ import annotations

import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
import contextlib

_FMI_WFS_URL = (
    "https://opendata.fmi.fi/wfs"
    "?service=WFS"
    "&version=2.0.0"
    "&request=getFeature"
    "&storedquery_id=fmi::observations::weather::simple"
    "&place=Helsinki"
    "&parameters=ws_10min,wd_10min,wg_10min"
    "&maxlocations=1"
)

_BsWfs_NS  = "http://xml.fmi.fi/schema/wfs/2.0"
CACHE_TTL  = 300  # seconds between FMI API polls
FETCH_TIMEOUT = 6  # seconds


@dataclass
class WeatherSnapshot:
    wind_speed_mps: float | None
    wind_dir_deg: float | None
    wave_height_m: float | None   # estimated from wind speed
    station_id: str = "Helsinki"
    fetched_at: float = 0.0

    @classmethod
    def null(cls) -> WeatherSnapshot:
        return cls(wind_speed_mps=None, wind_dir_deg=None, wave_height_m=None)


def _estimate_wave_height(wind_mps: float) -> float:
    """Simplified wind-speed → wave-height proxy for the Gulf of Finland."""
    if wind_mps < 3:
        return 0.1
    if wind_mps < 8:
        return round(0.1 + (wind_mps - 3) * 0.12, 2)
    if wind_mps < 14:
        return round(0.7 + (wind_mps - 8) * 0.25, 2)
    return round(2.2 + (wind_mps - 14) * 0.35, 2)


_cache: WeatherSnapshot | None = None


def fetch_weather() -> WeatherSnapshot:
    """Return a cached or freshly-fetched FMI weather snapshot."""
    global _cache
    now = time.monotonic()
    if _cache is not None and (now - _cache.fetched_at) < CACHE_TTL:
        return _cache

    try:
        with urllib.request.urlopen(_FMI_WFS_URL, timeout=FETCH_TIMEOUT) as resp:
            xml_bytes = resp.read()

        root = ET.fromstring(xml_bytes)
        params: dict[str, float] = {}
        tag = f"{{{_BsWfs_NS}}}BsWfsElement"
        name_tag = f"{{{_BsWfs_NS}}}ParameterName"
        val_tag  = f"{{{_BsWfs_NS}}}ParameterValue"

        for elem in root.iter(tag):
            name_el = elem.find(name_tag)
            val_el  = elem.find(val_tag)
            if name_el is not None and val_el is not None and val_el.text not in ("NaN", None, ""):
                with contextlib.suppress(ValueError):
                    params[name_el.text] = float(val_el.text)

        wind_speed = params.get("ws_10min")
        wave_h = _estimate_wave_height(wind_speed) if wind_speed is not None else None
        _cache = WeatherSnapshot(
            wind_speed_mps=wind_speed,
            wind_dir_deg=params.get("wd_10min"),
            wave_height_m=wave_h,
            fetched_at=now,
        )

    except Exception:  # noqa: BLE001
        snap = WeatherSnapshot.null()
        snap.fetched_at = now
        _cache = snap

    return _cache
