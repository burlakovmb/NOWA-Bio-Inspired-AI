"""One snapshot of the colony per tick, read through the zone adjacency matrix (issue #28).

Before the animals step, the runner records where every animal stands (Z: animal x zone), its public state, whether
it is eating and whether it is giving an alarm call. Per-zone groups are built once; what can be perceived from a
zone is its row of the adjacency matrix A (``sensor_system.ADJACENCY``) applied to them. Every animal then reads its
own zone's row instead of scanning the whole colony, and all of them read the same snapshot, so what an animal
perceives does not depend on the order in which the animals step. An alarm given during a tick is heard on the next
one.
"""

from __future__ import annotations

from typing import Any

from sensor_system import ADJACENCY, ZONE_INDEX, ZONES


class ZoneSnapshot:
    def __init__(self, animals: list[Any]) -> None:
        self.order: list[Any] = list(animals)
        self.index: dict[str, int] = {}
        self.by_id: dict[str, Any] = {}
        self.zone: dict[str, str] = {}
        self.public: dict[str, Any] = {}
        self.eating: dict[str, bool] = {}
        self.alarm_event: dict[str, int] = {}  # animal id -> event id, only for animals calling now
        members: dict[str, list[Any]] = {}
        for position, animal in enumerate(self.order):
            animal_id = str(animal.agent_id)
            if animal_id in self.by_id:
                continue  # the first one, as a scan of the colony found it
            self.index[animal_id] = position
            self.by_id[animal_id] = animal
            zone = str(animal.position)
            self.zone[animal_id] = zone
            self.public[animal_id] = animal.get_public_state()
            self.eating[animal_id] = str(getattr(animal, "current_action", "")) == "eat"
            # Asking every animal once per tick also samples its stress once per tick for the alarm rise.
            if animal._is_emitting_alarm():
                self.alarm_event[animal_id] = int(getattr(animal, "_alarm_event_id", 0))
            members.setdefault(zone, []).append(animal)
        self._members = members
        self._near: dict[str, list[Any]] = {}

    def near(self, zone: str) -> list[Any]:
        """Animals in ``zone`` or next to it, in colony order: the zone's row of A times Z."""
        zone = str(zone)
        cached = self._near.get(zone)
        if cached is not None:
            return cached
        row = ZONE_INDEX.get(zone)
        if row is None:  # a position outside the zone map only sees itself
            found = list(self._members.get(zone, []))
        else:
            found = [
                animal
                for col, linked in enumerate(ADJACENCY[row])
                if linked
                for animal in self._members.get(ZONES[col], [])
            ]
            found.sort(key=lambda animal: self.index[str(animal.agent_id)])
        self._near[zone] = found
        return found

    def eaters_in(self, zone: str) -> list[Any]:
        """Animals eating in ``zone`` itself (crowding at a bowl is not shared with the next zone)."""
        return [animal for animal in self._members.get(str(zone), []) if self.eating[str(animal.agent_id)]]
