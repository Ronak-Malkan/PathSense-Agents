"""
Tool functions for Fetch.ai agent integration.
Now using database backend instead of mock storage.
"""
from typing import Any, Optional, List
import json
from database import db_service


# ============================================================================
# FILE OPERATIONS (for backward compatibility with existing tests)
# ============================================================================

async def fetch_file(uri: str) -> bytes:
    """
    Fetch file contents from storage.

    Args:
        uri: File path or URI (bucket://path or file:///path)

    Returns:
        File contents as bytes

    Note: This is mainly for backward compatibility with file-based tests.
    In production, logs come from database.
    """
    try:
        import os
        from pathlib import Path

        # Handle file:/// URIs
        if uri.startswith("file:///"):
            path = uri.replace("file:///", "")
            path = str(Path(path))
        else:
            path = uri

        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(f"Could not fetch {uri}: {e}")


async def list_files(prefix: str, start: Optional[int] = None, end: Optional[int] = None) -> list[str]:
    """
    List files matching prefix and time range.

    Args:
        prefix: Path prefix (e.g., "logs/client_id/")
        start: Unix timestamp start (inclusive)
        end: Unix timestamp end (exclusive)

    Returns:
        List of file URIs

    Note: This is mainly for backward compatibility with file-based tests.
    In production, use database queries directly.
    """
    import os
    import glob

    pattern = f"{prefix}*.jsonl"
    files = glob.glob(pattern, recursive=True)

    return [f"file:///{f}" for f in files]


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

async def save_log_to_db(log_record: dict) -> int:
    """
    Save a log record to database.

    Args:
        log_record: Log record dictionary

    Returns:
        ID of inserted record
    """
    log = db_service.insert_log(log_record)
    return log.id


async def get_logs_from_db(
    client_id: str,
    session_id: Optional[str] = None,
    time_start: Optional[int] = None,
    time_end: Optional[int] = None,
    limit: Optional[int] = None
) -> List[dict]:
    """
    Retrieve logs from database.

    Args:
        client_id: User identifier
        session_id: Optional session filter
        time_start: Unix timestamp start
        time_end: Unix timestamp end
        limit: Maximum records to return

    Returns:
        List of log record dictionaries
    """
    logs = db_service.get_logs(
        client_id=client_id,
        session_id=session_id,
        time_start=time_start,
        time_end=time_end,
        limit=limit
    )
    return [log.to_dict() for log in logs]


# ============================================================================
# NOTIFICATION
# ============================================================================

async def notify(contact_id: str, payload: dict) -> bool:
    """
    Send alert notification to emergency contact.

    Args:
        contact_id: Emergency contact identifier
        payload: Alert payload (JSON-serializable dict)

    Returns:
        True if notification sent successfully
    """
    # Save alert to database
    alert_data = {
        "alert_type": payload.get("type", "unknown"),
        "client_id": payload.get("client_id", "unknown"),
        "contact_id": contact_id,
        "t": payload.get("t", 0),
        "rationale": payload.get("rationale"),
        "payload": payload
    }

    db_service.insert_alert(alert_data)

    # TODO: Actual notification implementation
    print(f"[ALERT] Notifying {contact_id}: {json.dumps(payload, indent=2)}")

    # TODO: Implement actual notification channels:
    # - Send SMS via Twilio
    # - Send email via SendGrid
    # - Push notification via Firebase Cloud Messaging
    # - Webhook to emergency dashboard

    return True


# ============================================================================
# INDEX PERSISTENCE
# ============================================================================

async def persist_index(key: str, value: Any) -> bool:
    """
    Persist index data to database.

    Args:
        key: Storage key (e.g., "index:client_id:session_id")
        value: JSON-serializable value (UserIndex dict)

    Returns:
        True if persisted successfully
    """
    # Parse key to extract client_id and session_id
    parts = key.split(":")
    if len(parts) < 2:
        return False

    client_id = parts[1]
    session_id = parts[2] if len(parts) > 2 else None

    # Extract time range from index data if available
    time_start = None
    time_end = None
    if isinstance(value, dict) and "by_time" in value:
        timestamps = list(value["by_time"].keys())
        if timestamps:
            time_start = min(timestamps)
            time_end = max(timestamps)

    db_service.save_index(
        client_id=client_id,
        index_data=value,
        session_id=session_id,
        time_start=time_start,
        time_end=time_end
    )

    return True


async def read_index(key: str) -> Optional[Any]:
    """
    Read index data from database.

    Args:
        key: Storage key (e.g., "index:client_id:session_id")

    Returns:
        Deserialized value or None if not found
    """
    # Parse key
    parts = key.split(":")
    if len(parts) < 2:
        return None

    client_id = parts[1]
    session_id = parts[2] if len(parts) > 2 else None

    return db_service.get_index(client_id=client_id, session_id=session_id)


# ============================================================================
# AUTHORIZATION
# ============================================================================

async def is_authorized(requester_id: str, client_id: str) -> bool:
    """
    Check if requester is authorized to access client data.

    Args:
        requester_id: ID of person making request
        client_id: ID of blind user whose data is being queried

    Returns:
        True if requester is in client's approved contacts
    """
    return db_service.is_authorized(requester_id, client_id)


async def add_authorized_contact(
    client_id: str,
    contact_id: str,
    contact_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
    contact_email: Optional[str] = None
) -> bool:
    """
    Add an emergency contact to client's authorized list.

    Args:
        client_id: User identifier
        contact_id: Emergency contact identifier
        contact_name: Contact name (optional)
        contact_phone: Contact phone (optional)
        contact_email: Contact email (optional)

    Returns:
        True if added successfully
    """
    db_service.add_emergency_contact(
        client_id=client_id,
        contact_id=contact_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email
    )
    return True


async def get_emergency_contacts(client_id: str) -> List[str]:
    """
    Get list of emergency contact IDs for a client.

    Args:
        client_id: User identifier

    Returns:
        List of contact IDs
    """
    contacts = db_service.get_emergency_contacts(client_id)
    return [contact.contact_id for contact in contacts]
