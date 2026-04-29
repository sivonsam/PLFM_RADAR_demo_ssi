#!/usr/bin/env python3
"""
Athene demo simulator — schema v1.0

Emits a continuous stream of JSON Lines (one RadarEvent per line) to stdout.
Output can be piped to the ingest step or directly to an event stream.

Usage examples
--------------
  # Offline: 14 synthetic tracks, 2 events/s
  python simulate_targets.py --rate 2

  # With live AIS from Digitraffic and FMI weather context
  python simulate_targets.py --live-ais --rate 1

  # Emit 100 events then exit (useful for testing)
  python simulate_targets.py --count 100 --no-weather

  # Pipe into the NDJSON ingest step
  python simulate_targets.py | python ../ingest/stdin_to_ndjson.py out/tracks.ndjson

Flags
-----
  --rate R        Events emitted per second across the whole track pool (default 1.0)
  --count N       Stop after N events; 0 = run forever (default 0)
  --dt S          Simulated time-step in seconds per pool tick (default 5.0)
  --live-ais      Fetch real vessel positions from Digitraffic and correlate
  --no-weather    Skip FMI weather fetch (useful offline / in CI)
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from ais_feed import AISVessel, fetch_ais
from archetypes import Track, initial_pool, respawn
from schema import Meta, RadarEvent, SeaState, TargetFields
from weather import WeatherSnapshot, fetch_weather


def _sea_state(snap: WeatherSnapshot) -> SeaState | None:
    if snap.wind_speed_mps is None:
        return None
    return SeaState(
        wave_height_m=snap.wave_height_m,
        wind_speed_mps=snap.wind_speed_mps,
        wind_dir_deg=snap.wind_dir_deg,
        station_id=snap.station_id,
    )


def _build_event(
    track: Track,
    session_id: str,
    sea: SeaState | None,
    ais_vessels: dict[int, AISVessel],
) -> RadarEvent:
    correlated = track.mmsi is not None and track.mmsi in ais_vessels
    live_cog   = ais_vessels[track.mmsi].cog if correlated else None
    return RadarEvent(
        event_id=RadarEvent.make_id(),
        event_type="radar_track",
        source="athene_sim+ais" if correlated else "athene_sim",
        timestamp_utc=RadarEvent.now_utc(),
        session_id=session_id,
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


def main() -> None:
    p = argparse.ArgumentParser(description="Athene radar track simulator")
    p.add_argument("--rate",       type=float, default=1.0, help="events/s (default 1.0)")
    p.add_argument("--count",      type=int,   default=0,   help="stop after N events; 0=forever")
    p.add_argument("--dt",         type=float, default=5.0, help="sim time-step seconds")
    p.add_argument("--live-ais",   action="store_true",     help="use live Digitraffic AIS")
    p.add_argument("--no-weather", action="store_true",     help="skip FMI weather fetch")
    args = p.parse_args()

    session_id = RadarEvent.make_id()
    pool       = initial_pool()
    interval   = 1.0 / max(args.rate, 0.001)
    emitted    = 0

    while True:
        weather  = fetch_weather() if not args.no_weather else WeatherSnapshot.null()
        ais      = fetch_ais()     if args.live_ais       else {}
        sea      = _sea_state(weather)

        for idx, track in enumerate(pool):
            track.step(args.dt)
            if track.out_of_bounds():
                pool[idx] = respawn(track)
                track = pool[idx]

            event = _build_event(track, session_id, sea, ais)
            sys.stdout.write(json.dumps(event.to_dict()) + "\n")
            sys.stdout.flush()

            emitted += 1
            if args.count and emitted >= args.count:
                return

            time.sleep(interval)


if __name__ == "__main__":
    main()
