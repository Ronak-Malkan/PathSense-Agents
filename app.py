"""
Flask API Server for Blind Navigation Agents
Provides REST API endpoints for YOLO app integration and agent communication.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

from indexer_agent import IndexerAgent
from query_agent import QueryAgent
from watchdog_agent import WatchdogAgent
from nav_types import LogRecord, QueryParams
from database import db_service
import tools

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

# Initialize database
db_service.init_db()

# Initialize agents
indexer_agent = IndexerAgent()
query_agent = QueryAgent()
watchdog_agent = WatchdogAgent()


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify server is running."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents": {
            "indexer": "active",
            "query": "active",
            "watchdog": "active"
        }
    }), 200


# ============================================================================
# YOLO APP ENDPOINTS (For Log Ingestion)
# ============================================================================

@app.route('/api/logs/ingest', methods=['POST'])
def ingest_log():
    """
    Receive a single log record from YOLO app.

    Request Body:
    {
        "client_id": "user_123",
        "session_id": "session_456",
        "t": 1732489200,
        "events": ["proceed"],
        "classes": ["person"],  // optional
        "free_ahead_m": 3.5,    // optional
        "confidence": 0.9,
        "app": "android-1.0.3"
    }

    Response:
    {
        "status": "success",
        "message": "Log record ingested",
        "processed_by": ["watchdog"]
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ["client_id", "session_id", "t", "events", "confidence"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400

        # Create LogRecord
        log_record: LogRecord = {
            "client_id": data["client_id"],
            "session_id": data["session_id"],
            "t": data["t"],
            "events": data["events"],
            "confidence": data["confidence"],
            "app": data.get("app", "unknown")
        }

        # Add optional fields
        if "classes" in data:
            log_record["classes"] = data["classes"]
        if "free_ahead_m" in data:
            log_record["free_ahead_m"] = data["free_ahead_m"]

        # Save to database
        log_id = asyncio.run(tools.save_log_to_db(log_record))

        # Process with WatchdogAgent (real-time monitoring)
        asyncio.run(watchdog_agent.process_record(log_record))

        return jsonify({
            "status": "success",
            "message": "Log record ingested",
            "log_id": log_id,
            "processed_by": ["database", "watchdog"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/logs/batch', methods=['POST'])
def ingest_batch_logs():
    """
    Receive batch of log records from YOLO app.

    Request Body:
    {
        "logs": [
            { /* LogRecord 1 */ },
            { /* LogRecord 2 */ },
            ...
        ]
    }

    Response:
    {
        "status": "success",
        "ingested": 100,
        "failed": 2,
        "errors": [...]
    }
    """
    try:
        data = request.get_json()
        logs = data.get("logs", [])

        ingested = 0
        failed = 0
        errors = []

        for idx, log_data in enumerate(logs):
            try:
                # Validate and create LogRecord
                log_record: LogRecord = {
                    "client_id": log_data["client_id"],
                    "session_id": log_data["session_id"],
                    "t": log_data["t"],
                    "events": log_data["events"],
                    "confidence": log_data["confidence"],
                    "app": log_data.get("app", "unknown")
                }

                if "classes" in log_data:
                    log_record["classes"] = log_data["classes"]
                if "free_ahead_m" in log_data:
                    log_record["free_ahead_m"] = log_data["free_ahead_m"]

                # Save to database
                asyncio.run(tools.save_log_to_db(log_record))

                # Process with WatchdogAgent
                asyncio.run(watchdog_agent.process_record(log_record))
                ingested += 1

            except Exception as e:
                failed += 1
                errors.append(f"Record {idx}: {str(e)}")

        return jsonify({
            "status": "success",
            "ingested": ingested,
            "failed": failed,
            "errors": errors[:10]  # Limit error list
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# INDEXER AGENT ENDPOINTS
# ============================================================================

@app.route('/api/index/build', methods=['POST'])
def build_index():
    """
    Build index for a specific client and time range.

    Request Body:
    {
        "client_id": "user_123",
        "time_start": 1732400000,  // optional
        "time_end": 1732489200,    // optional
        "session_id": "session_456" // optional
    }

    Response:
    {
        "status": "success",
        "client_id": "user_123",
        "records_processed": 1500,
        "dropped_records": 3,
        "almost_crashes": 5,
        "stuck_intervals": 2
    }
    """
    try:
        data = request.get_json()
        client_id = data.get("client_id")

        if not client_id:
            return jsonify({
                "status": "error",
                "message": "client_id is required"
            }), 400

        # Build index
        index = asyncio.run(indexer_agent.process_logs(
            client_id=client_id,
            time_start=data.get("time_start"),
            time_end=data.get("time_end"),
            session_id=data.get("session_id")
        ))

        return jsonify({
            "status": "success",
            "client_id": client_id,
            "records_processed": len(index["by_time"]),
            "dropped_records": index["dropped_records"],
            "almost_crashes": len(index["hazards"].get("almost_crash_moments", [])),
            "stuck_intervals": len(index["hazards"].get("stuck_intervals", [])),
            "event_counts": dict(index["counters"]),
            "class_counts": dict(index["by_class"])
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# QUERY AGENT ENDPOINTS
# ============================================================================

@app.route('/api/query', methods=['POST'])
def handle_query():
    """
    Answer natural language question about user navigation.

    Request Body:
    {
        "requester_id": "contact_001",
        "client_id": "user_123",
        "question": "How many times did he almost crash today?",
        "session_id": "session_456",  // optional
        "time_start": "today",         // or ISO 8601
        "time_end": "now",             // or ISO 8601
        "tz": "UTC"                    // optional
    }

    Response:
    {
        "status": "success",
        "answer": "5 near-miss events in the specified time window.",
        "response": {
            "client_id": "user_123",
            "time_window": {...},
            "metric": "almost_crash",
            "result": {"count": 5},
            "samples": [...]
        }
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        requester_id = data.get("requester_id")
        client_id = data.get("client_id")
        question = data.get("question")

        if not all([requester_id, client_id, question]):
            return jsonify({
                "status": "error",
                "message": "requester_id, client_id, and question are required"
            }), 400

        # Handle query
        answer, response = asyncio.run(query_agent.handle_query(
            requester_id=requester_id,
            client_id=client_id,
            question=question,
            session_id=data.get("session_id"),
            time_start=data.get("time_start"),
            time_end=data.get("time_end"),
            tz=data.get("tz", "UTC")
        ))

        return jsonify({
            "status": "success",
            "answer": answer,
            "response": response
        }), 200

    except PermissionError as e:
        return jsonify({
            "status": "error",
            "message": "Unauthorized",
            "detail": str(e)
        }), 403

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# WATCHDOG AGENT ENDPOINTS
# ============================================================================

@app.route('/api/watchdog/status/<client_id>', methods=['GET'])
def watchdog_status(client_id):
    """
    Get current watchdog monitoring status for a client.

    Response:
    {
        "client_id": "user_123",
        "records_in_window": 45,
        "last_record_time": 1732489200,
        "alerts": {
            "stuck": {"last_sent": 1732489000, "count": 2},
            "accident": {"last_sent": null, "count": 0}
        }
    }
    """
    try:
        window = list(watchdog_agent.client_windows.get(client_id, []))

        return jsonify({
            "client_id": client_id,
            "records_in_window": len(window),
            "last_record_time": window[-1]["t"] if window else None,
            "alerts": {
                "stuck": {
                    "last_sent": watchdog_agent.stuck_alerts.get(client_id),
                    "debounce_seconds": watchdog_agent.stuck_debounce
                },
                "accident": {
                    "last_sent": watchdog_agent.accident_alerts.get(client_id),
                    "debounce_seconds": watchdog_agent.accident_debounce
                }
            }
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/watchdog/clear/<client_id>', methods=['POST'])
def clear_watchdog_state(client_id):
    """
    Clear watchdog state for a client (e.g., session ended).

    Response:
    {
        "status": "success",
        "message": "Watchdog state cleared for user_123"
    }
    """
    try:
        watchdog_agent.clear_client_state(client_id)

        return jsonify({
            "status": "success",
            "message": f"Watchdog state cleared for {client_id}"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.route('/api/contacts/authorize', methods=['POST'])
def authorize_contact():
    """
    Add emergency contact to client's authorized list.

    Request Body:
    {
        "client_id": "user_123",
        "contact_id": "contact_456"
    }

    Response:
    {
        "status": "success",
        "message": "Contact authorized"
    }
    """
    try:
        data = request.get_json()
        client_id = data.get("client_id")
        contact_id = data.get("contact_id")

        if not all([client_id, contact_id]):
            return jsonify({
                "status": "error",
                "message": "client_id and contact_id are required"
            }), 400

        # Add to database
        asyncio.run(tools.add_authorized_contact(client_id, contact_id))

        # Also add to watchdog's in-memory cache
        if client_id not in watchdog_agent.emergency_contacts:
            watchdog_agent.emergency_contacts[client_id] = []

        if contact_id not in watchdog_agent.emergency_contacts[client_id]:
            watchdog_agent.emergency_contacts[client_id].append(contact_id)

        return jsonify({
            "status": "success",
            "message": f"Contact {contact_id} authorized for {client_id}",
            "contacts": watchdog_agent.emergency_contacts[client_id]
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get overall system statistics.

    Response:
    {
        "total_clients_monitored": 5,
        "total_logs_buffered": 1234,
        "active_sessions": 3,
        "uptime_seconds": 3600
    }
    """
    try:
        # Get database stats
        session = db_service.get_session()
        from database import LogRecord as DBLogRecord
        total_logs = session.query(DBLogRecord).count()
        total_clients = session.query(DBLogRecord.client_id).distinct().count()
        session.close()

        return jsonify({
            "total_clients_monitored": total_clients,
            "total_logs_in_db": total_logs,
            "active_watchdog_sessions": sum(1 for w in watchdog_agent.client_windows.values() if len(w) > 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found",
        "available_endpoints": [
            "GET  /health",
            "POST /api/logs/ingest",
            "POST /api/logs/batch",
            "POST /api/index/build",
            "POST /api/query",
            "GET  /api/watchdog/status/<client_id>",
            "POST /api/watchdog/clear/<client_id>",
            "POST /api/contacts/authorize",
            "GET  /api/stats"
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Blind Navigation Agents - Flask API Server")
    print("=" * 60)
    print("\nStarting server on http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /health                          - Health check")
    print("  POST /api/logs/ingest                 - Ingest single log")
    print("  POST /api/logs/batch                  - Ingest batch logs")
    print("  POST /api/index/build                 - Build user index")
    print("  POST /api/query                       - Query navigation data")
    print("  GET  /api/watchdog/status/<client_id> - Watchdog status")
    print("  POST /api/watchdog/clear/<client_id>  - Clear watchdog state")
    print("  POST /api/contacts/authorize          - Authorize contact")
    print("  GET  /api/stats                       - System statistics")
    print("\n" + "=" * 60)
    print("\nPress Ctrl+C to stop the server\n")

    # Run Flask app
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=5000,
        debug=True  # Enable debug mode for development
    )
