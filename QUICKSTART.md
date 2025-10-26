# Blind Navigation Agents - Quick Start Guide

## Overview

The system now uses a **database-backed architecture** where:
1. **YOLO app** sends logs to the Flask API
2. **Logs are stored** in a SQLite database
3. **Agents query** the database for processing

```
YOLO App → Flask API → SQLite Database
                            ↓
                    Agents Read & Process
```

---

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `flask` - API server
- `flask-cors` - Cross-origin support
- `sqlalchemy` - Database ORM
- `requests` - HTTP client
- `pytest` - Testing framework

### 2. Initialize the Database

```bash
python database.py
```

This creates `navigation_logs.db` with 4 tables:
- `log_records` - Navigation logs from YOLO app
- `user_indices` - Cached aggregations
- `alerts` - Alert history
- `emergency_contacts` - Authorized contacts

### 3. Start the API Server

```bash
python app.py
```

Server starts on `http://localhost:5000`

### 4. (Optional) Run Tests

```bash
python test_api.py
```

---

## How It Works

### Architecture Flow

```
┌─────────────┐
│  YOLO App   │ Sends log via HTTP POST
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│    Flask API (/api/logs/ingest)     │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│   Database (navigation_logs.db)     │
│   ┌─────────────────────────────┐   │
│   │ INSERT INTO log_records     │   │
│   └─────────────────────────────┘   │
└──────┬──────────────────────────────┘
       │
       ├─────► WatchdogAgent (real-time monitoring)
       │
       └─────► IndexerAgent (builds indices)
                    │
                    ▼
              QueryAgent (answers questions)
```

### Step-by-Step Example

#### Step 1: YOLO App Sends Log

```python
import requests
import time

log_data = {
    "client_id": "user_123",
    "session_id": "session_001",
    "t": int(time.time()),
    "events": ["proceed"],
    "confidence": 0.92,
    "free_ahead_m": 3.5,
    "classes": ["person"]
}

response = requests.post(
    'http://localhost:5000/api/logs/ingest',
    json=log_data
)
print(response.json())
```

#### Step 2: Log Saved to Database

```sql
-- Automatically executed by the API
INSERT INTO log_records (
    client_id, session_id, t, events,
    confidence, free_ahead_m, classes
) VALUES (
    'user_123', 'session_001', 1732489200,
    '["proceed"]', 0.92, 3.5, '["person"]'
);
```

#### Step 3: WatchdogAgent Monitors in Real-Time

```python
# Runs automatically when log is received
await watchdog_agent.process_record(log_record)
# Checks for stuck/accident patterns
# Sends alerts if needed
```

#### Step 4: Query Agent Answers Questions

```python
response = requests.post(
    'http://localhost:5000/api/query',
    json={
        "requester_id": "emergency_contact_001",
        "client_id": "user_123",
        "question": "How many near misses today?",
        "time_start": "today"
    }
)
```

The QueryAgent:
1. Fetches logs from database
2. Builds an index
3. Computes metrics
4. Returns natural language answer

---

## Database Schema

### Table: `log_records`

Stores all navigation logs from YOLO app.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (auto-increment) |
| client_id | STRING | User identifier |
| session_id | STRING | Navigation session ID |
| t | INTEGER | Unix timestamp |
| events | JSON | List of events ["proceed", "stop", etc.] |
| classes | JSON | YOLO detected classes |
| free_ahead_m | FLOAT | Free space ahead (meters) |
| confidence | FLOAT | Detection confidence (0-1) |
| app | STRING | App version |
| created_at | DATETIME | When record was inserted |

**Indices:**
- `idx_client_time` on (client_id, t)
- `idx_session_time` on (session_id, t)

### Table: `user_indices`

Caches computed aggregations for faster queries.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| client_id | STRING | User identifier |
| session_id | STRING | Session ID (optional) |
| time_start | INTEGER | Index time range start |
| time_end | INTEGER | Index time range end |
| index_data | JSON | Full index structure |
| created_at | DATETIME | When index was created |
| updated_at | DATETIME | Last update time |

### Table: `alerts`

Tracks all sent alerts for auditing and escalation.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| alert_type | STRING | stuck_alert, accident_alert |
| client_id | STRING | User identifier |
| contact_id | STRING | Emergency contact ID |
| t | INTEGER | Incident timestamp |
| rationale | TEXT | Why alert was sent |
| payload | JSON | Full alert payload |
| acknowledged | INTEGER | 0=no, 1=yes |
| created_at | DATETIME | When alert was sent |

### Table: `emergency_contacts`

Manages authorization for querying user data.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| client_id | STRING | User identifier |
| contact_id | STRING | Emergency contact ID |
| contact_name | STRING | Contact name (optional) |
| contact_phone | STRING | Phone number (optional) |
| contact_email | STRING | Email (optional) |
| authorized | INTEGER | 0=revoked, 1=active |
| created_at | DATETIME | When added |

---

## API Endpoints

### 1. Ingest Log (YOLO App → API)

**POST** `/api/logs/ingest`

```json
{
  "client_id": "user_123",
  "session_id": "session_001",
  "t": 1732489200,
  "events": ["proceed"],
  "confidence": 0.92,
  "free_ahead_m": 3.5
}
```

**What Happens:**
1. Log validated
2. Saved to `log_records` table
3. WatchdogAgent processes for real-time alerts
4. Returns success with `log_id`

### 2. Build Index

**POST** `/api/index/build`

```json
{
  "client_id": "user_123",
  "time_start": 1732400000,
  "time_end": 1732489200
}
```

**What Happens:**
1. Fetches logs from database
2. Builds aggregated index
3. Caches in `user_indices` table
4. Returns statistics

### 3. Query Data

**POST** `/api/query`

```json
{
  "requester_id": "contact_001",
  "client_id": "user_123",
  "question": "How many times did he almost crash today?"
}
```

**What Happens:**
1. Checks authorization in `emergency_contacts`
2. Fetches logs from database
3. Computes metrics
4. Returns natural language answer

### 4. Authorize Contact

**POST** `/api/contacts/authorize`

```json
{
  "client_id": "user_123",
  "contact_id": "emergency_contact_001"
}
```

**What Happens:**
1. Inserts into `emergency_contacts` table
2. Contact can now query user's data
3. Receives alerts for user

---

## Testing the System

### Test 1: Send Sample Logs

```bash
python test_api.py
```

This will:
- Send logs to the API
- Store them in database
- Trigger WatchdogAgent
- Run queries

### Test 2: Query Database Directly

```bash
python
```

```python
from database import db_service

# Get all logs for a user
logs = db_service.get_logs("user_123")
print(f"Found {len(logs)} logs")

# Get emergency contacts
contacts = db_service.get_emergency_contacts("user_123")
for contact in contacts:
    print(f"Contact: {contact.contact_id}")

# Get recent alerts
alerts = db_service.get_recent_alerts("user_123")
for alert in alerts:
    print(f"Alert: {alert.alert_type} at {alert.created_at}")
```

### Test 3: Inspect Database

```bash
# Install sqlite browser or use command line
sqlite3 navigation_logs.db

# View tables
.tables

# Query logs
SELECT * FROM log_records LIMIT 5;

# Count logs per user
SELECT client_id, COUNT(*) as count
FROM log_records
GROUP BY client_id;

# View recent alerts
SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
```

---

## Integration with YOLO App

### Python Example (for Android/Kivy)

```python
import requests
import time
from typing import List, Optional

class NavigationLogger:
    def __init__(self, api_url: str, client_id: str):
        self.api_url = api_url
        self.client_id = client_id
        self.session_id = f"session_{int(time.time())}"

    def log_event(
        self,
        events: List[str],
        confidence: float,
        free_ahead_m: Optional[float] = None,
        classes: Optional[List[str]] = None
    ):
        """Send log to API (saves to database)."""
        payload = {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "t": int(time.time()),
            "events": events,
            "confidence": confidence,
            "app": "yolo-android-1.0.3"
        }

        if free_ahead_m is not None:
            payload["free_ahead_m"] = free_ahead_m
        if classes:
            payload["classes"] = classes

        try:
            response = requests.post(
                f"{self.api_url}/api/logs/ingest",
                json=payload,
                timeout=5
            )
            if response.status_code == 200:
                return response.json().get("log_id")
        except Exception as e:
            print(f"Error logging: {e}")
            # Queue for retry

        return None

# Usage
logger = NavigationLogger(
    api_url="http://your-server:5000",
    client_id="user_123"
)

# After each YOLO detection
log_id = logger.log_event(
    events=["proceed"],
    confidence=0.92,
    free_ahead_m=3.5,
    classes=["person", "car"]
)
```

---

## Switching to Production Database

Currently using SQLite for development. For production:

### Option 1: PostgreSQL

```python
# In database.py, change:
DATABASE_URL = "postgresql://user:password@localhost/navigation_db"
```

### Option 2: MySQL

```python
# In database.py, change:
DATABASE_URL = "mysql://user:password@localhost/navigation_db"
```

### Option 3: Cloud Database

```python
# AWS RDS PostgreSQL
DATABASE_URL = "postgresql://user:pass@your-rds.amazonaws.com/navdb"

# Google Cloud SQL
DATABASE_URL = "postgresql://user:pass@/dbname?host=/cloudsql/project:region:instance"
```

---

## Troubleshooting

### Database doesn't exist

```bash
python database.py
```

### Can't connect to API

Make sure server is running:
```bash
python app.py
```

### Logs not appearing in database

Check API response:
```python
response = requests.post(...)
print(response.status_code)
print(response.json())
```

### Query fails with "Unauthorized"

Add emergency contact:
```python
requests.post(
    'http://localhost:5000/api/contacts/authorize',
    json={
        "client_id": "user_123",
        "contact_id": "your_contact_id"
    }
)
```

---

## Next Steps

1. ✅ System is ready for local testing
2. 🔄 Integrate with YOLO Android app
3. 🔄 Test with real navigation data
4. 🔄 Deploy to production server
5. 🔄 (Optional) Deploy to AgentVerse

For AgentVerse deployment, you'll need additional adapters to conform to their protocol.
