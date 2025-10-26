# Blind Navigation Monitoring Agents

AI-powered monitoring system for blind navigation assistance apps. Built with Flask, SQLAlchemy, and designed for YOLO-based Android navigation apps.

## Overview

This system consists of three specialized agents that work together to monitor navigation safety:

1. **IndexerAgent** - Processes and aggregates navigation logs from database
2. **QueryAgent** - Answers natural language questions about navigation history
3. **WatchdogAgent** - Real-time monitoring for emergencies (stuck, accidents)

## Architecture

```
YOLO Android App
    ↓ HTTP POST
Flask API (/api/logs/ingest)
    ↓ INSERT
SQLite Database (navigation_logs.db)
    ↓ SELECT
Agents (Indexer, Query, Watchdog)
    ↓ Alerts
Emergency Contacts
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python database.py
```

Creates `navigation_logs.db` with tables for logs, indices, alerts, and contacts.

### 3. Start API Server

```bash
python app.py
```

Server runs on `http://localhost:5000`

### 4. Test the System

```bash
python test_api.py
```

## Key Features

✅ **Database-Backed** - All logs persisted in SQLite (switchable to PostgreSQL/MySQL)
✅ **REST API** - Easy integration with YOLO Android app
✅ **Real-Time Monitoring** - WatchdogAgent detects emergencies immediately
✅ **Natural Language Queries** - Ask questions like "How many near misses today?"
✅ **Emergency Alerts** - Automatic notifications to authorized contacts
✅ **Scalable** - Ready for production deployment

## API Endpoints

### Ingest Log (YOLO App)

```bash
POST /api/logs/ingest
```

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

### Query Navigation Data

```bash
POST /api/query
```

```json
{
  "requester_id": "contact_001",
  "client_id": "user_123",
  "question": "How many near misses today?",
  "time_start": "today"
}
```

### Authorize Emergency Contact

```bash
POST /api/contacts/authorize
```

```json
{
  "client_id": "user_123",
  "contact_id": "emergency_contact_001"
}
```

See **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** for complete API reference.

## YOLO App Integration

### Python Example

```python
import requests
import time

class NavigationLogger:
    def __init__(self, api_url, client_id):
        self.api_url = api_url
        self.client_id = client_id
        self.session_id = f"session_{int(time.time())}"

    def log_event(self, events, confidence, free_ahead_m=None):
        response = requests.post(
            f"{self.api_url}/api/logs/ingest",
            json={
                "client_id": self.client_id,
                "session_id": self.session_id,
                "t": int(time.time()),
                "events": events,
                "confidence": confidence,
                "free_ahead_m": free_ahead_m
            }
        )
        return response.json()

# Usage
logger = NavigationLogger("http://localhost:5000", "user_123")
logger.log_event(["proceed"], 0.92, 3.5)
```

## Database Schema

### Tables

1. **log_records** - Navigation logs from YOLO app
2. **user_indices** - Cached aggregations for fast queries
3. **alerts** - Alert history for auditing
4. **emergency_contacts** - Authorized contacts for each user

See **[QUICKSTART.md](QUICKSTART.md)** for detailed schema documentation.

## Event Types

### Navigation Events
- `proceed` - Moving forward
- `stop` - Stationary
- `veer_left_*`, `veer_right_*` - Direction changes

### Obstacle Events
- `obstacle_center` - Obstacle ahead
- `obstacle_close` - Obstacle nearby
- `collision_warning` - Imminent collision

### Accident Events
- `fall`, `impact`, `collision`, `device_drop`

## Supported Queries

The QueryAgent understands natural language questions:

- "How many times did he almost crash?"
- "How many minutes was he stuck today?"
- "Show me near miss events"
- "Did he have an accident?"
- "What are the top obstacle classes?"

## Configuration

Edit thresholds in `nav_types.py`:

```python
CRASH_NEAR_M = 0.6          # Almost crash distance
STUCK_MIN_S = 120           # Minimum stuck duration
STUCK_ALERT_S = 300         # Alert after 5 minutes stuck
ACCIDENT_DEPTH_M = 0.4      # Critical depth threshold
```

## Production Deployment

### Switch to PostgreSQL

In `database.py`:

```python
DATABASE_URL = "postgresql://user:password@localhost/navigation_db"
```

### Switch to MySQL

```python
DATABASE_URL = "mysql://user:password@localhost/navigation_db"
```

### Cloud Database

```python
# AWS RDS
DATABASE_URL = "postgresql://user:pass@your-rds.amazonaws.com/navdb"
```

## Project Structure

```
blind_nav_agents/
├── app.py                  # Flask API server
├── database.py             # Database models and service layer
├── tools.py                # Database operations and utilities
├── nav_types.py            # Shared types and constants
├── indexer_agent.py        # Log indexing and aggregation
├── query_agent.py          # Natural language query handling
├── watchdog_agent.py       # Real-time emergency monitoring
├── test_api.py             # API test suite
├── requirements.txt        # Python dependencies
├── API_DOCUMENTATION.md    # Complete API reference
├── QUICKSTART.md           # Detailed setup guide
└── README.md               # This file
```

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Complete setup and usage guide
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** - Full API reference with examples

## Development

### Run Tests

```bash
python test_api.py
```

### View Database

```bash
sqlite3 navigation_logs.db
.tables
SELECT * FROM log_records LIMIT 5;
```

### Monitor Logs

```bash
tail -f app.log  # If logging is enabled
```

## Requirements

- Python 3.8+
- Flask
- SQLAlchemy
- pytest (for testing)

See `requirements.txt` for complete list.

## License

MIT License - Cal Hacks 2025

## Support

For issues or questions, check:
1. [QUICKSTART.md](QUICKSTART.md) for setup help
2. [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for API details
3. Database schema in [database.py](database.py)

Built for Cal Hacks Kotlin Android blind navigation app.
