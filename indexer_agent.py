"""
IndexerAgent: Reads logs from database, validates, and builds per-user indices.
"""
from typing import Optional
from datetime import datetime, timezone
from collections import defaultdict

from nav_types import (
    LogRecord, UserIndex, CRASH_NEAR_M, CONF_MIN, MERGE_WINDOW_S,
    OBSTACLE_EVENTS, is_obstacle_event
)
import tools


class IndexerAgent:
    """
    Reads new JSONL logs on schedule and builds searchable indices.

    Responsibilities:
    - Validate log schema
    - Drop corrupt lines
    - Build per-user, per-session indices
    - Persist compact aggregates
    """

    def __init__(self):
        self.name = "IndexerAgent"

    async def process_logs(
        self,
        client_id: str,
        time_start: Optional[int] = None,
        time_end: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> UserIndex:
        """
        Process all logs for a client in the given time range from DATABASE.

        Args:
            client_id: User identifier
            time_start: Unix timestamp start (optional)
            time_end: Unix timestamp end (optional)
            session_id: Filter by specific session (optional)

        Returns:
            UserIndex with aggregated data
        """
        # Initialize empty index
        index: UserIndex = {
            "client_id": client_id,
            "by_time": {},
            "by_event": defaultdict(list),
            "counters": defaultdict(int),
            "by_class": defaultdict(int),
            "hazards": {},
            "dropped_records": 0
        }

        # Fetch logs from database
        log_records = await tools.get_logs_from_db(
            client_id=client_id,
            session_id=session_id,
            time_start=time_start,
            time_end=time_end
        )

        # Process each record
        for log_dict in log_records:
            try:
                # Convert database dict to LogRecord format
                record = {
                    "client_id": log_dict["client_id"],
                    "session_id": log_dict["session_id"],
                    "t": log_dict["t"],
                    "events": log_dict["events"],
                    "confidence": log_dict["confidence"],
                    "app": log_dict.get("app", "unknown")
                }

                if log_dict.get("classes"):
                    record["classes"] = log_dict["classes"]
                if log_dict.get("free_ahead_m") is not None:
                    record["free_ahead_m"] = log_dict["free_ahead_m"]

                if not self._validate_record(record):
                    index["dropped_records"] += 1
                    continue

                # Add to index
                self._add_to_index(index, record)

            except Exception as e:
                print(f"Error processing record: {e}")
                index["dropped_records"] += 1
                continue

        # Convert defaultdicts to regular dicts for serialization
        index["by_event"] = dict(index["by_event"])
        index["counters"] = dict(index["counters"])
        index["by_class"] = dict(index["by_class"])

        # Compute hazard metrics
        index["hazards"] = self._compute_hazards(index)

        # Persist index
        key = f"index:{client_id}"
        if session_id:
            key += f":{session_id}"
        await tools.persist_index(key, index)

        return index

    def _validate_record(self, record: dict) -> bool:
        """
        Validate that record has required fields.

        Required: client_id, session_id, t, events, confidence
        """
        required = ["client_id", "session_id", "t", "events", "confidence"]
        for field in required:
            if field not in record:
                return False

        # Type checks
        if not isinstance(record["t"], int):
            return False
        if not isinstance(record["events"], list):
            return False
        if not isinstance(record["confidence"], (int, float)):
            return False
        if not 0 <= record["confidence"] <= 1:
            return False

        return True

    def _add_to_index(self, index: UserIndex, record: LogRecord):
        """Add validated record to all index structures."""
        t = record["t"]

        # by_time
        index["by_time"][t] = record

        # by_event
        for event in record["events"]:
            index["by_event"][event].append(t)
            index["counters"][event] += 1

        # by_class
        if "classes" in record and record["classes"]:
            for cls in record["classes"]:
                index["by_class"][cls] += 1

    def _compute_hazards(self, index: UserIndex) -> dict:
        """
        Compute derived hazard metrics from index.

        Returns:
            Dict with almost_crash_moments, stuck_intervals, etc.
        """
        hazards = {
            "almost_crash_moments": self._find_almost_crashes(index),
            "stuck_intervals": self._find_stuck_intervals(index)
        }
        return hazards

    def _find_almost_crashes(
        self,
        index: UserIndex,
        crash_near_m: float = CRASH_NEAR_M,
        conf_min: float = CONF_MIN
    ) -> list[dict]:
        """
        Find "almost crash" moments.

        Criteria:
        - Events contain obstacle_center/obstacle_close/collision_warning
        - free_ahead_m ≤ crash_near_m (if present)
        - confidence ≥ conf_min
        - Merge events within MERGE_WINDOW_S seconds

        Returns:
            List of moments with [t, free_ahead_m, classes, confidence]
        """
        candidates = []

        for t, record in index["by_time"].items():
            # Check events
            events = set(record["events"])
            if not events.intersection(OBSTACLE_EVENTS):
                continue

            # Check confidence
            if record["confidence"] < conf_min:
                continue

            # Check depth if available
            depth = record.get("free_ahead_m")
            if depth is not None and depth > crash_near_m:
                continue

            candidates.append({
                "t": t,
                "free_ahead_m": depth,
                "classes": record.get("classes", []),
                "confidence": record["confidence"],
                "events": list(events.intersection(OBSTACLE_EVENTS))
            })

        # Merge nearby events
        if not candidates:
            return []

        candidates.sort(key=lambda x: x["t"])
        merged = []
        current_group = [candidates[0]]

        for i in range(1, len(candidates)):
            if candidates[i]["t"] - current_group[-1]["t"] <= MERGE_WINDOW_S:
                current_group.append(candidates[i])
            else:
                # Take the closest/most critical from group
                best = min(current_group, key=lambda x: x["free_ahead_m"] or 999)
                merged.append(best)
                current_group = [candidates[i]]

        # Add last group
        if current_group:
            best = min(current_group, key=lambda x: x["free_ahead_m"] or 999)
            merged.append(best)

        return merged

    def _find_stuck_intervals(self, index: UserIndex, stuck_min_s: int = 120) -> list[dict]:
        """
        Find intervals where user was stationary.

        Stationary criteria:
        - "stop" in events OR
        - free_ahead_m variance < 0.05 m over window AND
        - no directional events

        Returns:
            List of intervals [start_t, end_t, duration_s]
        """
        from nav_types import is_directional_event, STUCK_VARIANCE_M, STUCK_GAP_S

        # Get all timestamped records sorted
        records = sorted(index["by_time"].items(), key=lambda x: x[0])

        intervals = []
        current_start = None
        current_end = None
        depths = []

        for t, record in records:
            events = record["events"]
            is_stopped = "stop" in events
            has_movement = any(is_directional_event(e) for e in events)

            # Check depth variance
            depth = record.get("free_ahead_m")
            if depth is not None:
                depths.append(depth)
                if len(depths) > 10:  # Keep rolling window
                    depths.pop(0)

            # Check if stationary
            depth_stationary = False
            if len(depths) >= 3:
                variance = max(depths) - min(depths)
                depth_stationary = variance < STUCK_VARIANCE_M

            is_stationary = (is_stopped or depth_stationary) and not has_movement

            if is_stationary:
                if current_start is None:
                    current_start = t
                current_end = t
            else:
                if current_start is not None:
                    duration = current_end - current_start
                    if duration >= stuck_min_s:
                        intervals.append({
                            "start_t": current_start,
                            "end_t": current_end,
                            "duration_s": duration
                        })
                    current_start = None
                    current_end = None
                    depths = []

        # Handle final interval
        if current_start is not None:
            duration = current_end - current_start
            if duration >= stuck_min_s:
                intervals.append({
                    "start_t": current_start,
                    "end_t": current_end,
                    "duration_s": duration
                })

        # Merge intervals with gaps ≤ STUCK_GAP_S
        if not intervals:
            return []

        merged = [intervals[0]]
        for interval in intervals[1:]:
            last = merged[-1]
            if interval["start_t"] - last["end_t"] <= STUCK_GAP_S:
                # Merge
                merged[-1] = {
                    "start_t": last["start_t"],
                    "end_t": interval["end_t"],
                    "duration_s": interval["end_t"] - last["start_t"]
                }
            else:
                merged.append(interval)

        return merged


# Example usage
async def main():
    """Example: Index logs for a client."""
    agent = IndexerAgent()

    # Process last 7 days
    import time
    now = int(time.time())
    week_ago = now - 7 * 24 * 3600

    index = await agent.process_logs(
        client_id="F7d...aK",
        time_start=week_ago,
        time_end=now
    )

    print(f"Processed {len(index['by_time'])} records")
    print(f"Dropped {index['dropped_records']} corrupt records")
    print(f"Events: {dict(index['counters'])}")
    print(f"Obstacle classes: {dict(index['by_class'])}")
    print(f"Almost crashes: {len(index['hazards']['almost_crash_moments'])}")
    print(f"Stuck intervals: {len(index['hazards']['stuck_intervals'])}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
