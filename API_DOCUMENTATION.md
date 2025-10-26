# Blind Navigation Agents - API Documentation

## Overview
This Flask API server provides REST endpoints for integrating the YOLO navigation app with the monitoring agents (IndexerAgent, QueryAgent, WatchdogAgent).

## Base URL
```
http://localhost:5000
```

---

## Endpoints

### 1. Health Check

**GET** `/health`

Check if the server is running and all agents are active.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-25T12:00:00Z",
  "agents": {
    "indexer": "active",
    "query": "active",
    "watchdog": "active"
  }
}
```

---

### 2. Ingest Single Log (YOLO App → Server)

**POST** `/api/logs/ingest`

Send a single navigation log record from the YOLO app to the agents.

**Request Body:**
```json
{
  "client_id": "user_123",
  "session_id": "session_456",
  "t": 1732489200,
  "events": ["proceed"],
  "classes": ["person"],
  "free_ahead_m": 3.5,
  "confidence": 0.9,
  "app": "android-1.0.3"
}
```

**Required Fields:** 
- `client_id` (string): User identifier
- `session_id` (string): Navigation session ID
- `t` (integer): Unix timestamp (seconds)
- `events` (array): List of event strings (e.g., "proceed", "stop", "obstacle_center")
- `confidence` (float): Detection confidence (0.0 to 1.0)

**Optional Fields:**
- `classes` (array): YOLO detected object classes
- `free_ahead_m` (float): Free space ahead in meters
- `app` (string): App version

**Response:**
```json
{
  "status": "success",
  "message": "Log record ingested",
  "processed_by": ["watchdog"],
  "timestamp": "2025-10-25T12:00:00Z"
}
```

**Usage in YOLO App:**
```python
import requests
import time

log_data = {
    "client_id": "user_123",
    "session_id": "session_001",
    "t": int(time.time()),
    "events": ["proceed"],
    "confidence": 0.85,
    "free_ahead_m": 2.5
}

response = requests.post(
    'http://localhost:5000/api/logs/ingest',
    json=log_data
)
print(response.json())
```

---

### 3. Ingest Batch Logs

**POST** `/api/logs/batch`

Send multiple log records at once (useful for offline sync).

**Request Body:**
```json
{
  "logs": [
    {
      "client_id": "user_123",
      "session_id": "session_456",
      "t": 1732489200,
      "events": ["proceed"],
      "confidence": 0.9
    },
    {
      "client_id": "user_123",
      "session_id": "session_456",
      "t": 1732489205,
      "events": ["obstacle_center"],
      "free_ahead_m": 0.5,
      "confidence": 0.85
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "ingested": 100,
  "failed": 2,
  "errors": ["Record 5: Missing required field: events"]
}
```

---

### 4. Build User Index

**POST** `/api/index/build`

Build or rebuild the navigation index for a specific user and time range.

**Request Body:**
```json
{
  "client_id": "user_123",
  "time_start": 1732400000,
  "time_end": 1732489200,
  "session_id": "session_456"
}
```

**Required:**
- `client_id` (string)

**Optional:**
- `time_start` (integer): Unix timestamp
- `time_end` (integer): Unix timestamp
- `session_id` (string): Filter by session

**Response:**
```json
{
  "status": "success",
  "client_id": "user_123",
  "records_processed": 1500,
  "dropped_records": 3,
  "almost_crashes": 5,
  "stuck_intervals": 2,
  "event_counts": {
    "proceed": 800,
    "stop": 200,
    "obstacle_center": 5
  },
  "class_counts": {
    "person": 50,
    "car": 30
  }
}
```

---

### 5. Query Navigation Data

**POST** `/api/query`

Ask natural language questions about user navigation history.

**Request Body:**
```json
{
  "requester_id": "contact_001",
  "client_id": "user_123",
  "question": "How many times did he almost crash today?",
  "session_id": "session_456",
  "time_start": "today",
  "time_end": "now",
  "tz": "UTC"
}
```

**Required:**
- `requester_id` (string): Emergency contact ID
- `client_id` (string): User being queried
- `question` (string): Natural language question

**Optional:**
- `session_id` (string)
- `time_start` (string): "today", "yesterday", "last_7d", or ISO 8601
- `time_end` (string): "now" or ISO 8601
- `tz` (string): Timezone (default: "UTC")

**Supported Questions:**
- "How many times did he almost crash?"
- "Show me near miss events"
- "How many minutes was he stuck?"
- "Did he have an accident?"
- "Show stuck intervals"

**Response:**
```json
{
  "status": "success",
  "answer": "5 near-miss events in the specified time window.",
  "response": {
    "client_id": "user_123",
    "time_window": {
      "start": "2025-10-25T00:00:00Z",
      "end": "2025-10-25T23:59:59Z",
      "tz": "UTC"
    },
    "metric": "almost_crash",
    "params": {
      "crash_near_m": 0.6,
      "stuck_min_s": 120,
      "conf_min": 0.6
    },
    "result": {
      "count": 5
    },
    "samples": [
      {
        "t": "2025-10-25T10:30:00Z",
        "free_ahead_m": 0.4,
        "confidence": 0.85,
        "events": ["obstacle_center"],
        "classes": ["person"]
      }
    ]
  }
}
```

**Error Response (Unauthorized):**
```json
{
  "status": "error",
  "message": "Unauthorized",
  "detail": "Unauthorized requester: contact_999"
}
```

---

### 6. Get Watchdog Status

**GET** `/api/watchdog/status/<client_id>`

Get real-time monitoring status for a user.

**Example:**
```
GET /api/watchdog/status/user_123
```

**Response:**
```json
{
  "client_id": "user_123",
  "records_in_window": 45,
  "last_record_time": 1732489200,
  "alerts": {
    "stuck": {
      "last_sent": 1732489000,
      "debounce_seconds": 900
    },
    "accident": {
      "last_sent": null,
      "debounce_seconds": 7200
    }
  }
}
```

---

### 7. Clear Watchdog State

**POST** `/api/watchdog/clear/<client_id>`

Clear monitoring state for a user (call when navigation session ends).

**Example:**
```
POST /api/watchdog/clear/user_123
```

**Response:**
```json
{
  "status": "success",
  "message": "Watchdog state cleared for user_123"
}
```

---

### 8. Authorize Emergency Contact

**POST** `/api/contacts/authorize`

Add an emergency contact to a user's authorized list.

**Request Body:**
```json
{
  "client_id": "user_123",
  "contact_id": "contact_456"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Contact contact_456 authorized for user_123",
  "contacts": ["contact_001", "contact_456"]
}
```

---

### 9. System Statistics

**GET** `/api/stats`

Get overall system statistics.

**Response:**
```json
{
  "total_clients_monitored": 5,
  "total_logs_buffered": 1234,
  "active_sessions": 3,
  "timestamp": "2025-10-25T12:00:00Z"
}
```

---

## Event Types

The YOLO app can send the following event types in the `events` array:

### Navigation Events
- `proceed` - Moving forward normally
- `stop` - User stopped
- `veer_left_10` - Veering left by 10 degrees
- `veer_right_15` - Veering right by 15 degrees

### Obstacle Events
- `obstacle_center` - Obstacle detected in center
- `obstacle_close` - Obstacle very close
- `collision_warning` - Imminent collision

### Accident Events
- `fall` - User fell
- `impact` - Impact detected
- `collision` - Collision occurred
- `device_drop` - Device dropped

---

## YOLO App Integration Example

### Python (Android/Kivy App)

```python
import requests
import time
from typing import List, Optional

class NavigationLogger:
    def __init__(self, api_url: str, client_id: str, session_id: str):
        self.api_url = api_url
        self.client_id = client_id
        self.session_id = session_id

    def send_log(
        self,
        events: List[str],
        confidence: float,
        classes: Optional[List[str]] = None,
        free_ahead_m: Optional[float] = None
    ):
        """Send single log record to agents."""
        log_data = {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "t": int(time.time()),
            "events": events,
            "confidence": confidence,
            "app": "android-1.0.3"
        }

        if classes:
            log_data["classes"] = classes
        if free_ahead_m is not None:
            log_data["free_ahead_m"] = free_ahead_m

        try:
            response = requests.post(
                f"{self.api_url}/api/logs/ingest",
                json=log_data,
                timeout=5
            )
            return response.json()
        except Exception as e:
            print(f"Error sending log: {e}")
            return None

# Usage in YOLO app
logger = NavigationLogger(
    api_url="http://your-server:5000",
    client_id="user_123",
    session_id="session_001"
)

# After YOLO detection
logger.send_log(
    events=["proceed"],
    confidence=0.92,
    classes=["person", "car"],
    free_ahead_m=3.5
)

# When obstacle detected
logger.send_log(
    events=["obstacle_center", "stop"],
    confidence=0.88,
    free_ahead_m=0.4
)
```

---

## Running the Server

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Server
```bash
python app.py
```

The server will start on `http://localhost:5000`

### 3. Test with curl
```bash
# Health check
curl http://localhost:5000/health

# Send log
curl -X POST http://localhost:5000/api/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "user_123",
    "session_id": "session_001",
    "t": 1732489200,
    "events": ["proceed"],
    "confidence": 0.9
  }'

# Query data
curl -X POST http://localhost:5000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "requester_id": "contact_001",
    "client_id": "user_123",
    "question": "How many near misses today?",
    "time_start": "today"
  }'
```

---

## Error Handling

All endpoints return errors in this format:

```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `400` - Bad request (missing required fields)
- `403` - Forbidden (unauthorized access)
- `404` - Endpoint not found
- `500` - Internal server error

---

## Security Considerations

For production deployment:

1. **Add Authentication**: Use API keys or JWT tokens
2. **Enable HTTPS**: Use SSL/TLS certificates
3. **Rate Limiting**: Prevent API abuse
4. **Input Validation**: Sanitize all inputs
5. **Database**: Replace mock storage with real database
6. **Logging**: Add structured logging for debugging

---

## Next Steps

1. Test the API locally with the provided test script
2. Integrate with your YOLO Android app
3. Configure emergency contact notifications
4. Deploy to production server or AgentVerse
5. Set up monitoring and alerting

For AgentVerse deployment, you'll need to create additional adapters to conform to their agent protocol.
