"""
WatchdogAgent: Streams new records and triggers alerts for emergencies.
"""
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from collections import defaultdict, deque

from nav_types import (
    LogRecord, Alert, STUCK_ALERT_S, ACCIDENT_EVENTS,
    ACCIDENT_PATTERN_WINDOW_S, ACCIDENT_NO_PROCEED_S,
    ACCIDENT_DEPTH_M, ACCIDENT_CONF, OBSTACLE_EVENTS,
    STUCK_VARIANCE_M, is_directional_event
)
import tools


class WatchdogAgent:
    """
    Streams new log records and detects emergencies in real-time.

    Features:
    - Detects stuck events (user stationary too long)
    - Detects accident patterns
    - Debouncing to avoid alert spam
    - Escalation for unacknowledged alerts
    """

    def __init__(self):
        self.name = "WatchdogAgent"

        # Per-client rolling windows
        self.client_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Alert state tracking
        self.stuck_alerts: Dict[str, int] = {}  # client_id → last_alert_time
        self.accident_alerts: Dict[str, int] = {}  # client_id → last_alert_time

        # Debounce periods (seconds)
        self.stuck_debounce = 900  # 15 minutes
        self.accident_debounce = 7200  # 2 hours

        # Contact mapping (TODO: load from database)
        self.emergency_contacts = {
            "F7d...aK": ["contact_001", "contact_002"],
            "test_client": ["emergency_contact_001"],  # For testing
            "demo_user": ["demo_contact_001"]  # For demo
        }

    async def process_record(self, record: LogRecord):
        """
        Process a new log record in real-time.

        Args:
            record: Fresh log record from Android app
        """
        client_id = record["client_id"]

        # Add to rolling window
        self.client_windows[client_id].append(record)

        # Check for stuck
        await self._check_stuck(client_id)

        # Check for accident
        await self._check_accident(client_id, record)

    async def _check_stuck(self, client_id: str):
        """
        Detect if user is stuck (stationary too long).

        Triggers alert after STUCK_ALERT_S seconds of no movement.
        """
        window = list(self.client_windows[client_id])
        if len(window) < 2:
            return

        # Check if user has been stationary
        now = int(time.time())
        stationary_start = None
        depths = []

        for record in reversed(window):
            t = record["t"]
            events = record["events"]

            # Check for movement
            is_stopped = "stop" in events
            has_movement = any(is_directional_event(e) for e in events)

            # Check depth variance
            depth = record.get("free_ahead_m")
            if depth is not None:
                depths.append(depth)
                if len(depths) > 10:
                    depths.pop(0)

            depth_stationary = False
            if len(depths) >= 3:
                variance = max(depths) - min(depths)
                depth_stationary = variance < STUCK_VARIANCE_M

            is_stationary = (is_stopped or depth_stationary) and not has_movement

            if is_stationary:
                stationary_start = t
            else:
                break  # Movement detected

        if stationary_start is None:
            return

        # Calculate duration
        duration = now - stationary_start

        if duration >= STUCK_ALERT_S:
            # Check debounce
            last_alert = self.stuck_alerts.get(client_id, 0)
            if now - last_alert >= self.stuck_debounce:
                await self._send_stuck_alert(client_id, stationary_start, duration)
                self.stuck_alerts[client_id] = now

    async def _check_accident(self, client_id: str, current_record: LogRecord):
        """
        Detect accident patterns from recent records.

        Patterns:
        1. Direct accident events (fall, impact, collision)
        2. Obstacle → stop → no proceed sequence
        3. Sudden veer surge → stop → no movement
        """
        events = set(current_record["events"])

        # Pattern 1: Direct accident events
        if events.intersection(ACCIDENT_EVENTS):
            await self._send_accident_alert(
                client_id,
                current_record["t"],
                f"Direct accident event: {events.intersection(ACCIDENT_EVENTS)}"
            )
            return

        # Pattern 2: Obstacle → stop → no proceed
        window = list(self.client_windows[client_id])
        if len(window) < 3:
            return

        # Look for recent obstacle with critical depth
        for i in range(len(window) - 1, max(0, len(window) - 10), -1):
            rec = window[i]
            rec_events = set(rec["events"])

            if not rec_events.intersection(OBSTACLE_EVENTS):
                continue
            if rec["confidence"] < ACCIDENT_CONF:
                continue

            depth = rec.get("free_ahead_m")
            if depth is None or depth > ACCIDENT_DEPTH_M:
                continue

            # Check if followed by stop and no movement
            obstacle_time = rec["t"]
            stop_found = False
            no_proceed_duration = 0

            for j in range(i + 1, len(window)):
                future_rec = window[j]
                future_t = future_rec["t"]
                future_events = set(future_rec["events"])

                if future_t - obstacle_time > ACCIDENT_PATTERN_WINDOW_S + ACCIDENT_NO_PROCEED_S:
                    break

                if "stop" in future_events:
                    stop_found = True

                if stop_found:
                    if any(is_directional_event(e) for e in future_events):
                        # Movement resumed
                        break
                    no_proceed_duration = future_t - obstacle_time

            if stop_found and no_proceed_duration >= ACCIDENT_NO_PROCEED_S:
                await self._send_accident_alert(
                    client_id,
                    obstacle_time,
                    f"Obstacle at {depth}m → stop → no movement for {no_proceed_duration}s"
                )
                return

        # Pattern 3: Veer surge → stop → stuck
        # Count recent veers
        veer_count = 0
        for rec in window[-5:]:  # Last 5 records
            events = rec["events"]
            veer_count += sum(1 for e in events if "veer" in e)

        if veer_count >= 3 and "stop" in current_record["events"]:
            # Check if stuck after veers
            time_since_last_move = 0
            for rec in reversed(window[-10:]):
                if any(is_directional_event(e) for e in rec["events"]):
                    break
                time_since_last_move = current_record["t"] - rec["t"]

            if time_since_last_move >= 120:  # 2 minutes no movement
                await self._send_accident_alert(
                    client_id,
                    current_record["t"],
                    f"Sudden veer surge ({veer_count} veers) followed by stop and {time_since_last_move}s no movement"
                )

    async def _send_stuck_alert(self, client_id: str, since: int, duration: int):
        """Send stuck alert to emergency contacts."""
        # Get contacts from database
        contacts = await tools.get_emergency_contacts(client_id)

        # Fallback to in-memory cache if no contacts in DB
        if not contacts:
            contacts = self.emergency_contacts.get(client_id, [])

        alert = Alert(
            alert_type="stuck_alert",
            client_id=client_id,
            t=int(time.time()),
            since=since
        )

        for contact_id in contacts:
            await tools.notify(contact_id, alert.to_dict())

        print(f"[WATCHDOG] Stuck alert sent for {client_id}: {duration}s stationary since {since}")

    async def _send_accident_alert(self, client_id: str, t: int, rationale: str):
        """Send accident alert to emergency contacts."""
        # Check debounce
        now = int(time.time())
        last_alert = self.accident_alerts.get(client_id, 0)
        if now - last_alert < self.accident_debounce:
            return  # Too soon

        # Get contacts from database
        contacts = await tools.get_emergency_contacts(client_id)

        # Fallback to in-memory cache if no contacts in DB
        if not contacts:
            contacts = self.emergency_contacts.get(client_id, [])

        alert = Alert(
            alert_type="accident_alert",
            client_id=client_id,
            t=t,
            rationale=rationale
        )

        for contact_id in contacts:
            await tools.notify(contact_id, alert.to_dict())

        self.accident_alerts[client_id] = now

        print(f"[WATCHDOG] Accident alert sent for {client_id}: {rationale}")

        # TODO: Escalate if unacknowledged in 2 minutes
        # Could use asyncio.create_task to schedule escalation check

    async def stream_logs(self, log_stream):
        """
        Main streaming loop.

        Args:
            log_stream: Async iterator yielding LogRecord objects

        Example:
            async for record in log_stream:
                await watchdog.process_record(record)
        """
        async for record in log_stream:
            await self.process_record(record)

    def clear_client_state(self, client_id: str):
        """Clear state for a client (e.g., session ended)."""
        if client_id in self.client_windows:
            self.client_windows[client_id].clear()
        self.stuck_alerts.pop(client_id, None)
        self.accident_alerts.pop(client_id, None)


# Example usage
async def simulate_streaming():
    """Simulate real-time log streaming."""
    watchdog = WatchdogAgent()

    # Simulate stuck scenario
    print("=== Simulating stuck scenario ===")
    base_time = int(time.time())

    for i in range(10):
        record: LogRecord = {
            "client_id": "F7d...aK",
            "session_id": "test-session",
            "t": base_time + i * 30,  # Every 30 seconds
            "events": ["stop"],
            "confidence": 0.8,
            "free_ahead_m": 1.5,
            "app": "android-1.0.3"
        }
        await watchdog.process_record(record)
        await asyncio.sleep(0.1)  # Simulate delay

    # Simulate accident scenario
    print("\n=== Simulating accident scenario ===")

    # Obstacle detected
    obstacle_record: LogRecord = {
        "client_id": "F7d...aK",
        "session_id": "test-session",
        "t": base_time + 400,
        "events": ["obstacle_center"],
        "classes": ["person"],
        "confidence": 0.85,
        "free_ahead_m": 0.3,
        "app": "android-1.0.3"
    }
    await watchdog.process_record(obstacle_record)

    # Stop
    stop_record: LogRecord = {
        "client_id": "F7d...aK",
        "session_id": "test-session",
        "t": base_time + 402,
        "events": ["stop"],
        "confidence": 0.9,
        "free_ahead_m": 0.3,
        "app": "android-1.0.3"
    }
    await watchdog.process_record(stop_record)

    # No movement for 35 seconds
    for i in range(7):
        stuck_record: LogRecord = {
            "client_id": "F7d...aK",
            "session_id": "test-session",
            "t": base_time + 407 + i * 5,
            "events": ["stop"],
            "confidence": 0.9,
            "free_ahead_m": 0.3,
            "app": "android-1.0.3"
        }
        await watchdog.process_record(stuck_record)

    print("\n=== Simulation complete ===")


async def main():
    """Run watchdog simulation."""
    await simulate_streaming()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
