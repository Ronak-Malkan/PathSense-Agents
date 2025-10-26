"""
Shared types and constants for blind navigation monitoring agents.
"""
from typing import TypedDict, Optional, Literal
from datetime import datetime
from dataclasses import dataclass


# Constants
CRASH_NEAR_M = 0.6  # Default threshold for "almost crash"
CONF_MIN = 0.6  # Minimum confidence for hazard detection
MERGE_WINDOW_S = 3  # Merge near-miss events within this window
STUCK_MIN_S = 120  # Minimum seconds to count as "stuck"
STUCK_ALERT_S = 300  # Alert emergency contacts after this duration
STUCK_VARIANCE_M = 0.05  # Max depth variance when stationary
STUCK_GAP_S = 10  # Max gap to merge stuck intervals
ACCIDENT_PATTERN_WINDOW_S = 5  # Window for accident pattern detection
ACCIDENT_NO_PROCEED_S = 30  # No movement after obstacle
ACCIDENT_DEPTH_M = 0.4  # Critical depth threshold
ACCIDENT_CONF = 0.7  # Confidence for accident patterns
CLOCK_SKEW_S = 5  # Acceptable timestamp jitter


# Log record schema
class LogRecord(TypedDict, total=False):
    """Single JSONL log record from Android app."""
    client_id: str
    session_id: str
    t: int  # Unix seconds
    events: list[str]
    classes: Optional[list[str]]
    free_ahead_m: Optional[float]
    confidence: float
    app: str


# Metric types
MetricType = Literal["almost_crash", "stuck_minutes", "stuck_intervals", "event_counts", "accident"]


# Query parameters
@dataclass
class QueryParams:
    """Parameters for metric computation."""
    crash_near_m: float = CRASH_NEAR_M
    stuck_min_s: int = STUCK_MIN_S
    conf_min: float = CONF_MIN

    def to_dict(self):
        return {
            "crash_near_m": self.crash_near_m,
            "stuck_min_s": self.stuck_min_s,
            "conf_min": self.conf_min
        }


# Time window
@dataclass
class TimeWindow:
    """Time range for queries."""
    start: datetime
    end: datetime
    tz: str = "UTC"

    def to_dict(self):
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "tz": self.tz
        }


# Index structures
class UserIndex(TypedDict):
    """Per-user aggregated indices."""
    client_id: str
    by_time: dict[int, LogRecord]  # timestamp → record
    by_event: dict[str, list[int]]  # event_name → [timestamps]
    counters: dict[str, int]  # event_name → count
    by_class: dict[str, int]  # YOLO class → count
    hazards: dict[str, any]  # Derived metrics cache
    dropped_records: int


# Alert types
@dataclass
class Alert:
    """Alert payload for emergency contacts."""
    alert_type: Literal["stuck_alert", "accident_alert"]
    client_id: str
    t: int
    rationale: Optional[str] = None
    since: Optional[int] = None

    def to_dict(self):
        return {
            "type": self.alert_type,
            "client_id": self.client_id,
            "t": self.t,
            "rationale": self.rationale,
            "since": self.since
        }


# Almost crash result
class AlmostCrashResult(TypedDict):
    """Almost crash metric result."""
    count: int
    examples: list[dict]


# Stuck result
class StuckResult(TypedDict):
    """Stuck metric result."""
    minutes: float
    intervals: list[tuple[str, str, int]]  # [start_iso, end_iso, duration_s]


# Event counts result
class EventCountsResult(TypedDict):
    """Event frequency result."""
    by_event: dict[str, int]
    by_class: dict[str, int]


# Accident result
class AccidentResult(TypedDict):
    """Accident detection result."""
    detected: bool
    first_t: Optional[int]
    rationale: Optional[str]
    supporting_records: list[dict]


# Query response
class QueryResponse(TypedDict):
    """Standard query response format."""
    client_id: str
    time_window: dict
    metric: MetricType
    params: dict
    result: dict
    samples: list[dict]


# Event categories for pattern matching
OBSTACLE_EVENTS = {"obstacle_center", "obstacle_close", "collision_warning"}
ACCIDENT_EVENTS = {"fall", "impact", "collision", "device_drop"}
DIRECTIONAL_EVENTS = {"veer_left", "veer_right", "proceed"}
STOP_EVENTS = {"stop"}


def is_directional_event(event: str) -> bool:
    """Check if event indicates movement."""
    return any(d in event for d in ["veer_left", "veer_right", "proceed"])


def is_obstacle_event(event: str) -> bool:
    """Check if event indicates obstacle."""
    return any(obs in event for obs in OBSTACLE_EVENTS)
