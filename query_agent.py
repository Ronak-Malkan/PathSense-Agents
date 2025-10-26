"""
QueryAgent: Answers natural language questions about user navigation logs.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from nav_types import (
    LogRecord, UserIndex, QueryParams, TimeWindow, QueryResponse,
    MetricType, ACCIDENT_EVENTS, ACCIDENT_PATTERN_WINDOW_S,
    ACCIDENT_NO_PROCEED_S, ACCIDENT_DEPTH_M, ACCIDENT_CONF,
    OBSTACLE_EVENTS, is_directional_event
)
import tools
from indexer_agent import IndexerAgent


class QueryAgent:
    """
    Answers natural language questions from authorized emergency contacts.

    Features:
    - NL intent classification
    - Deterministic metric computation
    - Authorization checking
    - Structured JSON + natural language responses
    """

    def __init__(self):
        self.name = "QueryAgent"
        self.indexer = IndexerAgent()

    async def handle_query(
        self,
        requester_id: str,
        client_id: str,
        question: str,
        session_id: Optional[str] = None,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
        tz: str = "UTC",
        params: Optional[QueryParams] = None
    ) -> Tuple[str, QueryResponse]:
        """
        Handle a natural language query.

        Args:
            requester_id: ID of person making request
            client_id: ID of blind user
            question: Natural language question
            session_id: Optional session filter
            time_start: ISO 8601 or relative (today, yesterday, last_7d)
            time_end: ISO 8601 or relative
            tz: Timezone (default UTC)
            params: Query parameters (thresholds)

        Returns:
            Tuple of (answer_text, QueryResponse)

        Raises:
            PermissionError: If requester not authorized
        """
        # Check authorization
        if not await tools.is_authorized(requester_id, client_id):
            raise PermissionError(f"Unauthorized requester: {requester_id}")

        # Parse time window
        time_window = self._parse_time_window(time_start, time_end, tz)

        # Default params
        if params is None:
            params = QueryParams()

        # Classify intent
        metric_type, intent_params = self._classify_intent(question)

        # Load or build index
        index = await self._load_index(
            client_id,
            session_id,
            int(time_window.start.timestamp()),
            int(time_window.end.timestamp())
        )

        # Compute metric
        result, samples = await self._compute_metric(
            metric_type,
            index,
            params,
            intent_params
        )

        # Format response
        answer = self._format_answer(metric_type, result, time_window)

        response: QueryResponse = {
            "client_id": client_id,
            "time_window": time_window.to_dict(),
            "metric": metric_type,
            "params": params.to_dict(),
            "result": result,
            "samples": samples[:3]  # Max 3 samples
        }

        return answer, response

    def _parse_time_window(
        self,
        start: Optional[str],
        end: Optional[str],
        tz: str
    ) -> TimeWindow:
        """
        Parse time window from relative or absolute strings.

        Supports: today, yesterday, last_7d, last_week, ISO 8601
        """
        now = datetime.now(timezone.utc)

        # Parse end time (default: now)
        if end is None or end == "now":
            end_dt = now
        elif end == "today":
            end_dt = now.replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        # Parse start time
        if start is None:
            start_dt = now - timedelta(days=7)  # Default: last week
        elif start == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # If end is None, set to end of today
            if end is None or end == "now":
                end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif start == "yesterday":
            yesterday = now - timedelta(days=1)
            start_dt = yesterday.replace(hour=0, minute=0, second=0)
            end_dt = yesterday.replace(hour=23, minute=59, second=59)
        elif start == "last_7d" or start == "last_week":
            start_dt = now - timedelta(days=7)
        else:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))

        return TimeWindow(start=start_dt, end=end_dt, tz=tz)

    def _classify_intent(self, question: str) -> Tuple[MetricType, dict]:
        """
        Classify natural language question into metric type.

        Returns:
            (metric_type, additional_params)
        """
        q_lower = question.lower()

        # Almost crash
        if any(kw in q_lower for kw in ["almost crash", "near miss", "collision warning", "close call"]):
            return "almost_crash", {}

        # Stuck intervals vs minutes
        if "stuck" in q_lower or "not moving" in q_lower or "stationary" in q_lower:
            if "interval" in q_lower or "when" in q_lower or "show" in q_lower:
                return "stuck_intervals", {}
            else:
                return "stuck_minutes", {}

        # Accident
        if any(kw in q_lower for kw in ["accident", "fell", "fall", "collision", "crashed", "impact"]):
            return "accident", {}

        # Event counts (default for "how many", "count", "top")
        return "event_counts", {}

    async def _load_index(
        self,
        client_id: str,
        session_id: Optional[str],
        time_start: int,
        time_end: int
    ) -> UserIndex:
        """
        Load index from cache or rebuild.
        """
        # Try to load cached index
        key = f"index:{client_id}"
        if session_id:
            key += f":{session_id}"

        cached = await tools.read_index(key)
        if cached:
            return cached

        # Rebuild index
        return await self.indexer.process_logs(
            client_id=client_id,
            time_start=time_start,
            time_end=time_end,
            session_id=session_id
        )

    async def _compute_metric(
        self,
        metric_type: MetricType,
        index: UserIndex,
        params: QueryParams,
        intent_params: dict
    ) -> Tuple[dict, list[dict]]:
        """
        Compute requested metric from index.

        Returns:
            (result_dict, sample_records)
        """
        if metric_type == "almost_crash":
            return self._compute_almost_crash(index, params)
        elif metric_type == "stuck_minutes":
            return self._compute_stuck_minutes(index, params)
        elif metric_type == "stuck_intervals":
            return self._compute_stuck_intervals(index, params)
        elif metric_type == "accident":
            return self._compute_accident(index, params)
        else:  # event_counts
            return self._compute_event_counts(index, params)

    def _compute_almost_crash(
        self,
        index: UserIndex,
        params: QueryParams
    ) -> Tuple[dict, list[dict]]:
        """Compute almost crash count."""
        moments = index["hazards"].get("almost_crash_moments", [])

        # Filter by params
        filtered = [
            m for m in moments
            if m["confidence"] >= params.conf_min
            and (m["free_ahead_m"] is None or m["free_ahead_m"] <= params.crash_near_m)
        ]

        result = {"count": len(filtered)}

        # Format samples
        samples = []
        for m in filtered[:3]:
            samples.append({
                "t": datetime.fromtimestamp(m["t"], tz=timezone.utc).isoformat(),
                "free_ahead_m": m["free_ahead_m"],
                "confidence": m["confidence"],
                "events": m["events"],
                "classes": m["classes"]
            })

        return result, samples

    def _compute_stuck_minutes(
        self,
        index: UserIndex,
        params: QueryParams
    ) -> Tuple[dict, list[dict]]:
        """Compute total stuck minutes."""
        intervals = index["hazards"].get("stuck_intervals", [])

        # Filter by minimum duration
        filtered = [i for i in intervals if i["duration_s"] >= params.stuck_min_s]

        total_seconds = sum(i["duration_s"] for i in filtered)
        total_minutes = round(total_seconds / 60, 1)

        result = {"minutes": total_minutes}

        # Samples
        samples = []
        for interval in filtered[:3]:
            start_iso = datetime.fromtimestamp(interval["start_t"], tz=timezone.utc).isoformat()
            end_iso = datetime.fromtimestamp(interval["end_t"], tz=timezone.utc).isoformat()
            samples.append({
                "start": start_iso,
                "end": end_iso,
                "duration_s": interval["duration_s"]
            })

        return result, samples

    def _compute_stuck_intervals(
        self,
        index: UserIndex,
        params: QueryParams
    ) -> Tuple[dict, list[dict]]:
        """Compute stuck intervals."""
        intervals = index["hazards"].get("stuck_intervals", [])

        # Filter by minimum duration
        filtered = [i for i in intervals if i["duration_s"] >= params.stuck_min_s]

        result_intervals = []
        for interval in filtered:
            start_iso = datetime.fromtimestamp(interval["start_t"], tz=timezone.utc).isoformat()
            end_iso = datetime.fromtimestamp(interval["end_t"], tz=timezone.utc).isoformat()
            result_intervals.append([start_iso, end_iso, interval["duration_s"]])

        result = {"intervals": result_intervals}

        # Samples are the intervals themselves
        samples = [
            {
                "start": iv[0],
                "end": iv[1],
                "duration_s": iv[2]
            }
            for iv in result_intervals[:3]
        ]

        return result, samples

    def _compute_accident(
        self,
        index: UserIndex,
        params: QueryParams
    ) -> Tuple[dict, list[dict]]:
        """Detect accident patterns."""
        records = sorted(index["by_time"].items(), key=lambda x: x[0])

        # Pattern 1: Direct accident events
        for t, rec in records:
            events = set(rec["events"])
            if events.intersection(ACCIDENT_EVENTS):
                result = {
                    "detected": True,
                    "first_t": t,
                    "rationale": f"Direct accident event: {events.intersection(ACCIDENT_EVENTS)}"
                }
                sample = {
                    "t": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                    "events": list(events),
                    "confidence": rec["confidence"]
                }
                return result, [sample]

        # Pattern 2: Obstacle → stop → no proceed
        for i, (t, rec) in enumerate(records):
            events = set(rec["events"])
            if not events.intersection(OBSTACLE_EVENTS):
                continue
            if rec["confidence"] < ACCIDENT_CONF:
                continue

            depth = rec.get("free_ahead_m")
            if depth is None or depth > ACCIDENT_DEPTH_M:
                continue

            # Look ahead for stop + no proceed
            stop_found = False
            no_proceed_duration = 0

            for j in range(i + 1, len(records)):
                t2, rec2 = records[j]
                if t2 - t > ACCIDENT_PATTERN_WINDOW_S + ACCIDENT_NO_PROCEED_S:
                    break

                events2 = set(rec2["events"])
                if "stop" in events2:
                    stop_found = True

                if stop_found:
                    if any(is_directional_event(e) for e in events2):
                        # Movement resumed
                        break
                    no_proceed_duration = t2 - t

            if stop_found and no_proceed_duration >= ACCIDENT_NO_PROCEED_S:
                result = {
                    "detected": True,
                    "first_t": t,
                    "rationale": f"Obstacle at {depth}m → stop → no movement for {no_proceed_duration}s"
                }
                sample = {
                    "t": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                    "events": list(events),
                    "free_ahead_m": depth,
                    "confidence": rec["confidence"]
                }
                return result, [sample]

        # No accident detected
        result = {"detected": False, "first_t": None, "rationale": "No accident patterns found"}
        return result, []

    def _compute_event_counts(
        self,
        index: UserIndex,
        params: QueryParams
    ) -> Tuple[dict, list[dict]]:
        """Compute event and class frequencies."""
        result = {
            "by_event": dict(index["counters"]),
            "by_class": dict(index["by_class"])
        }

        # Sample top events
        top_events = sorted(
            index["counters"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        samples = [{"event": e, "count": c} for e, c in top_events]

        return result, samples

    def _format_answer(
        self,
        metric_type: MetricType,
        result: dict,
        time_window: TimeWindow
    ) -> str:
        """Format natural language answer."""
        if metric_type == "almost_crash":
            count = result["count"]
            return f"{count} near-miss event{'s' if count != 1 else ''} in the specified time window."

        elif metric_type == "stuck_minutes":
            minutes = result["minutes"]
            return f"{minutes} minutes stationary in the specified time window."

        elif metric_type == "stuck_intervals":
            intervals = result["intervals"]
            return f"{len(intervals)} stuck interval{'s' if len(intervals) != 1 else ''} found."

        elif metric_type == "accident":
            if result["detected"]:
                return f"Accident detected at {datetime.fromtimestamp(result['first_t'], tz=timezone.utc).isoformat()}. {result['rationale']}"
            else:
                return "No accident detected in the specified time window."

        else:  # event_counts
            total = sum(result["by_event"].values())
            return f"{total} total events logged in the specified time window."


# Example usage
async def main():
    """Example: Query agent for almost crashes."""
    agent = QueryAgent()

    answer, response = await agent.handle_query(
        requester_id="contact_001",
        client_id="F7d...aK",
        question="Give me the number of times this guy almost crashed into something last week.",
        time_start="last_7d",
        tz="UTC"
    )

    print(f"Answer: {answer}\n")
    print("JSON Response:")
    import json
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
