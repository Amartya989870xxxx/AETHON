"""Scripted demo scenarios.

Each function plants the exact traffic pattern one alert rule is designed to
catch. Nothing here tells the alert engine what to find — it plants a vehicle
behaving a certain way and the engine has to notice on its own. That
distinction is what makes the demo a demonstration rather than a puppet show.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .simulator import TrafficSimulator, VehiclePass, random_plate


@dataclass
class Scenario:
    key: str
    plate: str
    title: str
    expect: str          # which alert rule should fire
    narrative: str       # what an operator would be told
    passes: list[VehiclePass]


def blacklisted_vehicle(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """A watch-listed plate drives a normal route across the city.

    Nothing about its *behaviour* is unusual — it is caught purely because the
    plate is on the registry. This proves the blacklist path independently of
    the anomaly rules.
    """
    route = sim.graph.path_between("C15", "C05") or ["C15", "C01", "C02", "C03", "C04", "C05"]
    passes = sim.journey(start, plate=plate, route=route, vehicle_type="suv")
    return Scenario(
        "blacklist", plate, "Watch-listed vehicle enters the city",
        "blacklist_hit",
        f"{plate} is on the watch list and was picked up entering via the airport "
        f"expressway, then tracked across {len(route)} cameras.",
        passes,
    )


def cloned_plate(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """Two vehicles carrying the same plate, in two places at once.

    The give-away is not the plate text — it is that the road graph says no
    single vehicle could have made both sightings. This is the case a naive
    "sort by timestamp" tracker silently stitches into one impossible journey.
    """
    west = sim.journey(start, plate=plate, route=["C09", "C12", "C01"], vehicle_type="sedan")
    # Same minute, opposite side of the city — physically impossible for one car.
    east = sim.journey(start + timedelta(seconds=90), plate=plate,
                       route=["C04", "C05", "C06"], vehicle_type="sedan")
    return Scenario(
        "clone", plate, "Same plate seen on opposite sides of the city",
        "impossible_travel",
        f"{plate} was read at the west gate and, 90 seconds later, on the "
        f"south-east ring — {'a journey no vehicle can make'}. Likely a cloned "
        f"or forged plate.",
        west + east,
    )


def restricted_zone_entry(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """An unregistered vehicle enters the restricted industrial corridor."""
    passes = sim.journey(start, plate=plate, route=["C13", "C10", "C11"], vehicle_type="truck")
    return Scenario(
        "restricted", plate, "Unpermitted entry into a restricted corridor",
        "restricted_zone",
        f"{plate} entered the restricted industrial corridor via the Hospital "
        f"Junction spur.",
        passes,
    )


def loitering(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """A vehicle circling the same central zone for well over an hour.

    Each individual sighting is unremarkable. The pattern across them is not.
    """
    loop = ["C07", "C14", "C03", "C02", "C01", "C08", "C07"]
    passes: list[VehiclePass] = []
    ts = start
    for lap in range(3):
        leg = sim.journey(ts, plate=plate, route=loop, vehicle_type="hatchback")
        passes.extend(leg)
        ts = leg[-1].timestamp + timedelta(minutes=4)
    return Scenario(
        "loiter", plate, "Vehicle circling the central business district",
        "loitering",
        f"{plate} completed three loops of the central zone over "
        f"{round((passes[-1].timestamp - passes[0].timestamp).total_seconds()/60)} minutes.",
        passes,
    )


def odd_hours(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """A vehicle with a settled daytime commute suddenly moving at 3am.

    The rule compares the plate against *its own* history, not a global curfew,
    so a night-shift vehicle that always drives at 3am never trips it.
    """
    passes: list[VehiclePass] = []
    # Establish a routine: same morning commute for several days.
    for day in range(4):
        commute = start.replace(hour=9, minute=10) - timedelta(days=4 - day)
        passes.extend(sim.journey(commute, plate=plate,
                                  route=["C09", "C08", "C07", "C13"],
                                  vehicle_type="sedan"))
    # Then break it.
    night = start.replace(hour=3, minute=20)
    passes.extend(sim.journey(night, plate=plate,
                              route=["C13", "C10", "C11"], vehicle_type="sedan"))
    return Scenario(
        "odd_hours", plate, "Vehicle breaks its own established routine",
        "odd_hours",
        f"{plate} has a four-day record of 09:00 commutes on the west radial. "
        f"Tonight it moved at 03:20 into the industrial corridor.",
        passes,
    )


def missed_detection(sim: TrafficSimulator, start: datetime, plate: str) -> Scenario:
    """A clean run with one camera's reading deliberately deleted.

    Proves the trajectory engine bridges the gap using road-graph travel times
    instead of breaking the route in two.
    """
    route = ["C15", "C01", "C02", "C03", "C04"]
    passes = sim.journey(start, plate=plate, route=route, vehicle_type="hatchback")
    # C02 goes offline for this vehicle.
    passes = [p for p in passes if p.camera_id != "C02"]
    return Scenario(
        "missed", plate, "Camera outage mid-route",
        "none",
        f"{plate} was not reported by C02 (offline). The trajectory engine "
        f"should still return one continuous route, flagging the bridged hop.",
        passes,
    )


ALL_SCENARIOS = [
    blacklisted_vehicle, cloned_plate, restricted_zone_entry,
    loitering, odd_hours, missed_detection,
]


def build_all(sim: TrafficSimulator, start: datetime,
              rng: random.Random | None = None) -> list[Scenario]:
    """Instantiate every scenario with a distinct, well-formed plate."""
    rng = rng or random.Random(99)
    out: list[Scenario] = []
    for fn in ALL_SCENARIOS:
        out.append(fn(sim, start, random_plate(rng)))
    return out
