"""The road network as a graph of cameras.

This is the structure that makes city-wide correlation possible. Two sightings
of a plate only become a *trajectory* if the road network says the vehicle
could physically have made that journey in the elapsed time. Everything the
trajectory matcher rules out, it rules out using this graph.

Edges are road-network distances, not straight-line — a river between two
cameras 400m apart may mean a 6km drive, and a matcher using haversine
distance would accept an impossible hop.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Camera, CameraLink

# Compass headings in degrees, for direction-consistency scoring.
HEADINGS = {
    "north": 0, "northeast": 45, "east": 90, "southeast": 135,
    "south": 180, "southwest": 225, "west": 270, "northwest": 315,
}


@dataclass(frozen=True)
class CameraNode:
    camera_id: str
    name: str
    lat: float
    lon: float
    road_segment: str
    zone: str
    facing_direction: str
    lanes: int
    is_restricted: bool


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Used only as a sanity floor on road distance."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def heading_delta(a: str, b: str) -> float:
    """Smallest angle between two compass directions, in degrees."""
    if a not in HEADINGS or b not in HEADINGS:
        return 90.0                      # unknown -> neutral, neither helps nor hurts
    diff = abs(HEADINGS[a] - HEADINGS[b]) % 360
    return min(diff, 360 - diff)


class CameraGraph:
    """In-memory road graph. Small enough (thousands of nodes) to hold
    resident; rebuilt when the camera topology changes."""

    def __init__(self, nodes: dict[str, CameraNode], graph: nx.DiGraph):
        self.nodes = nodes
        self.g = graph

    # ---- construction ----------------------------------------------------
    @classmethod
    def from_db(cls, db: Session) -> "CameraGraph":
        cams = db.execute(select(Camera)).scalars().all()
        links = db.execute(select(CameraLink)).scalars().all()
        nodes = {
            c.camera_id: CameraNode(
                c.camera_id, c.name, c.lat, c.lon, c.road_segment, c.zone,
                c.facing_direction, c.lanes, c.is_restricted,
            )
            for c in cams
        }
        g = nx.DiGraph()
        for cam_id in nodes:
            g.add_node(cam_id)
        for l in links:
            if l.from_camera in nodes and l.to_camera in nodes:
                g.add_edge(
                    l.from_camera, l.to_camera,
                    distance_km=l.distance_km,
                    heading=l.heading,
                    road_name=l.road_name,
                    speed_limit=l.speed_limit_kmph,
                )
        return cls(nodes, g)

    # ---- queries ---------------------------------------------------------
    def has_node(self, cam: str) -> bool:
        return cam in self.nodes

    @lru_cache(maxsize=8192)
    def _shortest(self, a: str, b: str):
        """Cached Dijkstra: (road_distance_km, hop_count) or None if
        unreachable. Cache is keyed per graph instance."""
        if a not in self.g or b not in self.g:
            return None
        try:
            path = nx.dijkstra_path(self.g, a, b, weight="distance_km")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        dist = sum(
            self.g[u][v]["distance_km"] for u, v in zip(path, path[1:])
        )
        return dist, len(path) - 1, path

    def road_distance_km(self, a: str, b: str) -> float | None:
        r = self._shortest(a, b)
        return r[0] if r else None

    def hop_count(self, a: str, b: str) -> int | None:
        """Number of camera-to-camera edges on the shortest path.

        A hop count above 1 means the vehicle passed cameras that did not
        report it — either a missed detection or an offline camera. The
        trajectory matcher tolerates this up to a configured limit instead of
        breaking the path, which is what keeps trajectories intact in the real
        world.
        """
        r = self._shortest(a, b)
        return r[1] if r else None

    def path_between(self, a: str, b: str) -> list[str] | None:
        r = self._shortest(a, b)
        return r[2] if r else None

    def travel_window_seconds(self, a: str, b: str) -> tuple[float, float] | None:
        """Physically plausible travel-time range between two cameras.

        Derived from road distance and the urban speed envelope. This range is
        the core of the matcher: a sighting pair outside it is not the same
        vehicle, no matter how well the plate text matches.
        """
        dist = self.road_distance_km(a, b)
        if dist is None:
            return None
        cfg = settings.trajectory
        fastest = (dist / cfg.max_speed_kmph) * 3600.0
        slowest = (dist / cfg.min_speed_kmph) * 3600.0
        return fastest, slowest

    def direction_score(self, observed_direction: str, a: str, b: str) -> float:
        """Does the heading observed at camera A point toward camera B?

        1.0 = travelling straight toward B, 0.0 = travelling away from it.
        Unknown directions score a neutral 0.5 so a camera that cannot measure
        heading degrades the match rather than vetoing it.
        """
        if not observed_direction or observed_direction == "unknown":
            return 0.5
        path = self.path_between(a, b)
        if not path or len(path) < 2:
            return 0.5
        edge_heading = self.g[path[0]][path[1]].get("heading")
        if not edge_heading:
            return 0.5
        delta = heading_delta(observed_direction, edge_heading)
        return round(max(0.0, 1.0 - (delta / 180.0)), 4)

    def zone_of(self, cam: str) -> str | None:
        node = self.nodes.get(cam)
        return node.zone if node else None

    def is_restricted(self, cam: str) -> bool:
        node = self.nodes.get(cam)
        return bool(node and node.is_restricted)

    def summary(self) -> dict:
        return {
            "cameras": len(self.nodes),
            "links": self.g.number_of_edges(),
            "zones": sorted({n.zone for n in self.nodes.values()}),
            "restricted_cameras": [c for c, n in self.nodes.items() if n.is_restricted],
            "strongly_connected": nx.is_strongly_connected(self.g) if self.g.number_of_nodes() else False,
        }
