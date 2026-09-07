"""A synthetic but structurally realistic city camera network.

Sixteen cameras across six zones, wired into a connected road graph with a
ring road, radial spokes and an industrial spur. Distances are derived from
real coordinates and inflated by a winding factor, because road distance is
always longer than straight-line — the trajectory matcher depends on that
distinction being honest.

This stands in for a city's real camera inventory during development. Loading
a real deployment means replacing this one file with the operator's camera
list and road graph; nothing downstream changes.
"""
from __future__ import annotations

import math

from ..engines.camera_graph import haversine_km

# Road distance is longer than straight-line distance. 1.35 is a typical
# detour index for a dense Indian urban grid.
WINDING_FACTOR = 1.35

# camera_id, name, lat, lon, road_segment, zone, facing, lanes, restricted
CAMERAS = [
    ("C01", "Airport Road North Gate",   12.9950, 77.5900, "NH-44-North",     "north",      "south", 4, False),
    ("C02", "Ring Road North Junction",  12.9910, 77.6010, "ORR-North",       "north",      "east",  3, False),
    ("C03", "MG Road East Entry",        12.9820, 77.6150, "MG-Road",         "east",       "south", 3, False),
    ("C04", "Whitefield Corridor",       12.9750, 77.6300, "Whitefield-Main", "east",       "south", 4, False),
    ("C05", "Silk Board Flyover",        12.9600, 77.6220, "ORR-South-East",  "south",      "west",  5, False),
    ("C06", "South Ring Underpass",      12.9550, 77.6000, "ORR-South",       "south",      "west",  4, False),
    ("C07", "City Centre Square",        12.9760, 77.5960, "Central-Ave",     "central",    "north", 3, False),
    ("C08", "Market Street North",       12.9800, 77.5900, "Market-St",       "central",    "north", 2, False),
    ("C09", "West Gate Toll",            12.9790, 77.5700, "NH-48-West",      "west",       "east",  4, False),
    ("C10", "Industrial Estate Gate",    12.9680, 77.5620, "Industrial-Link", "industrial", "north", 2, True),
    ("C11", "Peenya Link Road",          12.9720, 77.5560, "Industrial-Link", "industrial", "east",  2, True),
    ("C12", "Outer Ring West",           12.9880, 77.5750, "ORR-West",        "west",       "north", 3, False),
    ("C13", "Hospital Junction",         12.9700, 77.5980, "Central-Ave",     "central",    "south", 3, False),
    ("C14", "Stadium Approach",          12.9730, 77.6080, "Stadium-Rd",      "central",    "east",  2, False),
    ("C15", "Airport Expressway KM12",   13.0050, 77.5850, "NH-44-North",     "north",      "south", 6, False),
    ("C16", "South Bypass Toll",         12.9500, 77.5900, "Bypass-South",    "south",      "west",  4, False),
]

# Undirected road connections; each becomes two directed edges.
ROADS = [
    ("C15", "C01", "NH-44"),        ("C01", "C02", "ORR"),
    ("C02", "C03", "ORR"),          ("C03", "C04", "Whitefield Main"),
    ("C04", "C05", "ORR-SE"),       ("C05", "C06", "ORR-South"),
    ("C06", "C16", "Bypass"),       ("C16", "C10", "Industrial Access"),
    ("C10", "C11", "Peenya Link"),  ("C11", "C09", "NH-48"),
    ("C09", "C12", "ORR-West"),     ("C12", "C01", "ORR-NW"),
    ("C01", "C08", "Market St"),    ("C08", "C07", "Central Ave"),
    ("C07", "C13", "Central Ave"),  ("C13", "C06", "South Radial"),
    ("C07", "C14", "Stadium Rd"),   ("C14", "C03", "Stadium Rd"),
    ("C09", "C08", "West Radial"),  ("C13", "C10", "Industrial Spur"),
    ("C14", "C05", "East Radial"),
    # The bypass matters: without it the only south-to-west route runs through
    # the restricted industrial corridor, so every transiting vehicle would
    # trip the restricted-zone rule. Real cities route through-traffic around
    # controlled areas, and the graph has to reflect that.
    ("C16", "C09", "West Bypass"),
]

SPEED_LIMITS = {
    "NH-44": 80.0, "ORR": 60.0, "ORR-SE": 60.0, "ORR-South": 60.0,
    "ORR-West": 60.0, "ORR-NW": 60.0, "Bypass": 70.0, "NH-48": 80.0,
    "Whitefield Main": 50.0, "Market St": 40.0, "Central Ave": 40.0,
    "Stadium Rd": 40.0, "South Radial": 50.0, "West Radial": 45.0,
    "Industrial Access": 50.0, "Industrial Spur": 45.0, "Peenya Link": 45.0,
    "East Radial": 50.0, "West Bypass": 70.0,
}

_COMPASS = ["north", "northeast", "east", "southeast",
            "south", "southwest", "west", "northwest"]


def bearing_to_compass(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Great-circle bearing snapped to an 8-point compass direction.

    Deriving headings from coordinates rather than hand-labelling them keeps
    the graph self-consistent — a mislabelled heading would silently poison
    the direction-consistency term in trajectory scoring.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return _COMPASS[int((deg + 22.5) % 360 // 45)]


def build_camera_rows() -> list[dict]:
    return [
        {
            "camera_id": cid, "name": name, "lat": lat, "lon": lon,
            "road_segment": seg, "zone": zone, "facing_direction": facing,
            "lanes": lanes, "is_restricted": restricted, "active": True,
            "calibration": {"mounting_height_m": 6.0, "focal_mm": 12.0},
        }
        for cid, name, lat, lon, seg, zone, facing, lanes, restricted in CAMERAS
    ]


def build_link_rows() -> list[dict]:
    """Two directed edges per road, each with its own heading."""
    coords = {c[0]: (c[2], c[3]) for c in CAMERAS}
    rows: list[dict] = []
    for a, b, road in ROADS:
        (lat_a, lon_a), (lat_b, lon_b) = coords[a], coords[b]
        dist = round(haversine_km(lat_a, lon_a, lat_b, lon_b) * WINDING_FACTOR, 4)
        limit = SPEED_LIMITS.get(road, 50.0)
        rows.append({"from_camera": a, "to_camera": b, "distance_km": dist,
                     "heading": bearing_to_compass(lat_a, lon_a, lat_b, lon_b),
                     "road_name": road, "speed_limit_kmph": limit})
        rows.append({"from_camera": b, "to_camera": a, "distance_km": dist,
                     "heading": bearing_to_compass(lat_b, lon_b, lat_a, lon_a),
                     "road_name": road, "speed_limit_kmph": limit})
    return rows
