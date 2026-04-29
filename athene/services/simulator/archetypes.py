"""
Gulf of Finland vessel archetypes for the Athene demo simulator.

The track pool contains N persistent Track objects that move realistically
each time-step.  When a track leaves the demo area it is replaced (respawned)
with a fresh instance of the same vessel type.

Pool composition (ARCHETYPE_MIX):
  2 Helsinki-Tallinn ferries  - fast, scheduled corridor, always AIS-visible
  4 cargo vessels             - slow east-west transit, AIS-visible
  6 small craft               — archipelago area, some without AIS
  1 patrol vessel             — structured route, always AIS-visible
  1 dark target               — radar return only, NO AIS  ← anomaly trigger
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field

# ── Demo area ────────────────────────────────────────────────────────────────
GOF_LAT_MIN, GOF_LAT_MAX = 59.30, 60.50
GOF_LON_MIN, GOF_LON_MAX = 22.50, 27.50

# ── Key waypoints (lat, lon) ─────────────────────────────────────────────────
WP_HELSINKI_PORT = (60.155, 24.956)
WP_TALLINN_PORT  = (59.446, 24.750)
WP_WEST_ENTRY    = (59.80,  22.90)
WP_EAST_ENTRY    = (60.10,  27.00)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, in degrees [0, 360)."""
    d_lon = math.radians(lon2 - lon1)
    r1, r2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(d_lon) * math.cos(r2)
    y = math.cos(r1) * math.sin(r2) - math.sin(r1) * math.cos(r2) * math.cos(d_lon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _move(
    lat: float, lon: float, heading_deg: float, speed_mps: float, dt_s: float
) -> tuple[float, float]:
    """Advance a geographic point by speed_mps for dt_s seconds."""
    dist_m = speed_mps * dt_s
    earth_r = 6_371_000.0
    d = dist_m / earth_r
    lat1, lon1 = math.radians(lat), math.radians(lon)
    h = math.radians(heading_deg)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(h))
    lon2 = lon1 + math.atan2(
        math.sin(h) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 6), round(math.degrees(lon2), 6)


# ── Track ─────────────────────────────────────────────────────────────────────

@dataclass
class Track:
    """A single persistent radar/vessel track in the simulated pool."""
    target_id: str
    vessel_type: str
    track_type: str          # "confirmed" | "dark" | "unknown"
    mmsi: int | None
    vessel_name: str | None
    lat: float
    lon: float
    speed_mps: float
    heading_deg: float
    confidence: float
    scenario: str | None = None
    _waypoints: list[tuple[float, float]] = field(default_factory=list, repr=False)
    _wp_index: int = field(default=0, repr=False)

    def step(self, dt_s: float = 5.0) -> None:
        """Advance the track by dt_s seconds of simulated time."""
        if self._waypoints:
            self._steer_to_waypoint(dt_s)
        else:
            self.heading_deg = (self.heading_deg + random.gauss(0, 3)) % 360
            self.lat, self.lon = _move(self.lat, self.lon, self.heading_deg, self.speed_mps, dt_s)

    def _steer_to_waypoint(self, dt_s: float) -> None:
        if self._wp_index >= len(self._waypoints):
            self._wp_index = 0
        wp = self._waypoints[self._wp_index]
        target_bearing = _bearing(self.lat, self.lon, wp[0], wp[1])
        diff = ((target_bearing - self.heading_deg + 180) % 360) - 180
        self.heading_deg = (self.heading_deg + max(-5.0, min(5.0, diff))) % 360
        self.lat, self.lon = _move(self.lat, self.lon, self.heading_deg, self.speed_mps, dt_s)
        dist_m = math.sqrt(((self.lat - wp[0]) * 111_000) ** 2 + ((self.lon - wp[1]) * 65_000) ** 2)
        if dist_m < 600:
            self._wp_index += 1

    def out_of_bounds(self) -> bool:
        lat_ok = GOF_LAT_MIN <= self.lat <= GOF_LAT_MAX
        lon_ok = GOF_LON_MIN <= self.lon <= GOF_LON_MAX
        return not (lat_ok and lon_ok)


# ── Archetype factories ───────────────────────────────────────────────────────

_FERRY_NAMES   = ["VIKING GRACE", "SILJA EUROPA", "TALLINK STAR", "BALTIC QUEEN", "ROMANTIKA"]
_CARGO_NAMES   = ["FINNWAVE", "BORE SONG", "AMANDA C", "DELTA SENATOR", "KRISTINA"]
_PATROL_NAMES  = ["TURVA", "MERIKARHU", "TURSAS"]


def make_helsinki_tallinn_ferry() -> Track:
    """Helsinki-Tallinn ferry on the classic 85 km corridor (~18-22 kn)."""
    outbound  = random.choice([True, False])
    start     = WP_HELSINKI_PORT if outbound else WP_TALLINN_PORT
    if outbound:
        waypoints = [WP_TALLINN_PORT, WP_HELSINKI_PORT]
    else:
        waypoints = [WP_HELSINKI_PORT, WP_TALLINN_PORT]
    lat = start[0] + random.uniform(-0.02, 0.02)
    lon = start[1] + random.uniform(-0.02, 0.02)
    return Track(
        target_id=str(uuid.uuid4()),
        vessel_type="ferry",
        track_type="confirmed",
        mmsi=random.randint(230_000_000, 230_999_999),
        vessel_name=random.choice(_FERRY_NAMES),
        lat=lat, lon=lon,
        speed_mps=round(random.uniform(9.5, 11.5), 2),
        heading_deg=_bearing(lat, lon, waypoints[0][0], waypoints[0][1]),
        confidence=round(random.uniform(0.92, 0.99), 2),
        scenario="ferry_route",
        _waypoints=list(waypoints),
    )


def make_cargo_vessel() -> Track:
    """Slow cargo vessel transiting east-west across the Gulf (~9-15 kn)."""
    westbound = random.choice([True, False])
    start = WP_EAST_ENTRY if westbound else WP_WEST_ENTRY
    end   = WP_WEST_ENTRY if westbound else WP_EAST_ENTRY
    lat = start[0] + random.uniform(-0.15, 0.15)
    lon = start[1] + random.uniform(-0.10, 0.10)
    mid = (
        (start[0] + end[0]) / 2 + random.uniform(-0.05, 0.05),
        (start[1] + end[1]) / 2 + random.uniform(-0.10, 0.10),
    )
    country_mmsi_range = random.choice([
        (230_000_000, 230_999_999),  # Finland
        (276_000_000, 276_999_999),  # Estonia
        (265_000_000, 265_999_999),  # Sweden
    ])
    return Track(
        target_id=str(uuid.uuid4()),
        vessel_type="cargo",
        track_type="confirmed",
        mmsi=random.randint(*country_mmsi_range),
        vessel_name=random.choice(_CARGO_NAMES),
        lat=lat, lon=lon,
        speed_mps=round(random.uniform(4.5, 7.5), 2),
        heading_deg=_bearing(lat, lon, mid[0], mid[1]),
        confidence=round(random.uniform(0.85, 0.96), 2),
        scenario="cargo_transit",
        _waypoints=[mid, end],
    )


def make_small_craft() -> Track:
    """Small leisure or fishing craft near the Helsinki archipelago."""
    lat = 60.05 + random.uniform(-0.12, 0.12)
    lon = 24.85 + random.uniform(-0.25, 0.25)
    has_ais = random.random() > 0.35
    return Track(
        target_id=str(uuid.uuid4()),
        vessel_type="small_craft",
        track_type="confirmed" if has_ais else "unknown",
        mmsi=random.randint(230_000_000, 230_999_999) if has_ais else None,
        vessel_name=None,
        lat=lat, lon=lon,
        speed_mps=round(random.uniform(1.5, 5.0), 2),
        heading_deg=round(random.uniform(0, 359.9), 1),
        confidence=round(random.uniform(0.70, 0.88), 2),
        scenario="small_craft",
    )


def make_patrol_vessel() -> Track:
    """Finnish Border Guard / Navy patrol on a structured triangular route."""
    wp1 = (59.90, 24.20)
    wp2 = (60.05, 25.10)
    wp3 = (59.85, 25.50)
    lat = wp1[0] + random.uniform(-0.05, 0.05)
    lon = wp1[1] + random.uniform(-0.05, 0.05)
    return Track(
        target_id=str(uuid.uuid4()),
        vessel_type="patrol",
        track_type="confirmed",
        mmsi=random.randint(230_000_000, 230_999_999),
        vessel_name=random.choice(_PATROL_NAMES),
        lat=lat, lon=lon,
        speed_mps=round(random.uniform(7.5, 12.0), 2),
        heading_deg=_bearing(lat, lon, wp2[0], wp2[1]),
        confidence=round(random.uniform(0.94, 0.99), 2),
        scenario="patrol",
        _waypoints=[wp1, wp2, wp3, wp1],
    )


def make_dark_target() -> Track:
    """
    Dark target: emits a radar return but broadcasts NO AIS signal.
    Positioned near a busy shipping lane — the primary anomaly demo trigger.
    The AI dark-target agent will flag this as suspicious after 10 minutes.
    """
    lat = 59.75 + random.uniform(-0.08, 0.08)
    lon = 25.30 + random.uniform(-0.15, 0.15)
    return Track(
        target_id=str(uuid.uuid4()),
        vessel_type="dark",
        track_type="dark",
        mmsi=None,
        vessel_name=None,
        lat=lat, lon=lon,
        speed_mps=round(random.uniform(2.0, 4.5), 2),
        heading_deg=round(random.uniform(0, 359.9), 1),
        confidence=round(random.uniform(0.72, 0.85), 2),
        scenario="dark_target",
    )


# ── Pool management ───────────────────────────────────────────────────────────

ARCHETYPE_MIX: list[tuple] = [
    (make_helsinki_tallinn_ferry, 2),
    (make_cargo_vessel,           4),
    (make_small_craft,            6),
    (make_patrol_vessel,          1),
    (make_dark_target,            1),
]

_VESSEL_TYPE_FACTORIES = {
    "ferry":       make_helsinki_tallinn_ferry,
    "cargo":       make_cargo_vessel,
    "small_craft": make_small_craft,
    "patrol":      make_patrol_vessel,
    "dark":        make_dark_target,
}


def initial_pool() -> list[Track]:
    """Build the starting track pool from ARCHETYPE_MIX."""
    pool: list[Track] = []
    for factory, count in ARCHETYPE_MIX:
        pool.extend(factory() for _ in range(count))
    return pool


def respawn(track: Track) -> Track:
    """Replace an out-of-bounds track with a fresh one of the same vessel type."""
    factory = _VESSEL_TYPE_FACTORIES.get(track.vessel_type, make_small_craft)
    return factory()
