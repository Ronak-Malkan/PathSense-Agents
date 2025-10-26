"""
Database layer for blind navigation agents.
Uses SQLAlchemy ORM with SQLite (can switch to PostgreSQL/MySQL).
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, DateTime, Index, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timezone
from typing import Optional, List, Dict
import json

# Database configuration
DATABASE_URL = "sqlite:///./navigation_logs.db"
# For PostgreSQL: "postgresql://user:password@localhost/navigation_db"
# For MySQL: "mysql://user:password@localhost/navigation_db"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False  # Set to True for SQL query debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# ============================================================================
# DATABASE MODELS
# ============================================================================

class LogRecord(Base):
    """Table for storing navigation log records from YOLO app."""
    __tablename__ = "log_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    t = Column(Integer, nullable=False, index=True)  # Unix timestamp
    events = Column(JSON, nullable=False)  # List of event strings
    classes = Column(JSON, nullable=True)  # List of YOLO classes
    free_ahead_m = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False)
    app = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Composite indices for common queries
    __table_args__ = (
        Index('idx_client_time', 'client_id', 't'),
        Index('idx_session_time', 'session_id', 't'),
        Index('idx_client_session', 'client_id', 'session_id'),
    )

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "session_id": self.session_id,
            "t": self.t,
            "events": self.events,
            "classes": self.classes,
            "free_ahead_m": self.free_ahead_m,
            "confidence": self.confidence,
            "app": self.app,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class UserIndex(Base):
    """Table for storing computed user indices (cached aggregations)."""
    __tablename__ = "user_indices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    time_start = Column(Integer, nullable=True)
    time_end = Column(Integer, nullable=True)
    index_data = Column(JSON, nullable=False)  # Full index structure
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_client_index', 'client_id', 'session_id'),
    )

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "session_id": self.session_id,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "index_data": self.index_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class Alert(Base):
    """Table for storing sent alerts (for tracking and escalation)."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_type = Column(String(50), nullable=False, index=True)  # stuck_alert, accident_alert
    client_id = Column(String(255), nullable=False, index=True)
    contact_id = Column(String(255), nullable=False)
    t = Column(Integer, nullable=False)  # Timestamp of incident
    rationale = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    acknowledged = Column(Integer, default=0)  # 0 = no, 1 = yes
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_client_alert', 'client_id', 'alert_type', 'created_at'),
    )

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "client_id": self.client_id,
            "contact_id": self.contact_id,
            "t": self.t,
            "rationale": self.rationale,
            "payload": self.payload,
            "acknowledged": bool(self.acknowledged),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class EmergencyContact(Base):
    """Table for managing emergency contacts and authorizations."""
    __tablename__ = "emergency_contacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_id = Column(String(255), nullable=False, index=True)
    contact_id = Column(String(255), nullable=False, index=True)
    contact_name = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(255), nullable=True)
    authorized = Column(Integer, default=1)  # 0 = revoked, 1 = active
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_client_contact', 'client_id', 'contact_id'),
    )

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "contact_id": self.contact_id,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "authorized": bool(self.authorized),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# ============================================================================
# DATABASE SERVICE LAYER
# ============================================================================

class DatabaseService:
    """Service layer for database operations."""

    def __init__(self):
        self.engine = engine

    def get_session(self) -> Session:
        """Get a new database session."""
        return SessionLocal()

    def init_db(self):
        """Initialize database (create all tables)."""
        Base.metadata.create_all(bind=self.engine)
        print("✓ Database initialized successfully")

    def drop_all(self):
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(bind=self.engine)
        print("✓ All tables dropped")

    # ========================================================================
    # LOG RECORDS
    # ========================================================================

    def insert_log(self, log_data: dict) -> LogRecord:
        """
        Insert a single log record.

        Args:
            log_data: Dictionary with log record fields

        Returns:
            Created LogRecord object
        """
        session = self.get_session()
        try:
            log = LogRecord(
                client_id=log_data["client_id"],
                session_id=log_data["session_id"],
                t=log_data["t"],
                events=log_data["events"],
                classes=log_data.get("classes"),
                free_ahead_m=log_data.get("free_ahead_m"),
                confidence=log_data["confidence"],
                app=log_data.get("app", "unknown")
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
        finally:
            session.close()

    def insert_logs_batch(self, logs_data: List[dict]) -> int:
        """
        Insert multiple log records in batch.

        Args:
            logs_data: List of log record dictionaries

        Returns:
            Number of records inserted
        """
        session = self.get_session()
        try:
            logs = [
                LogRecord(
                    client_id=log["client_id"],
                    session_id=log["session_id"],
                    t=log["t"],
                    events=log["events"],
                    classes=log.get("classes"),
                    free_ahead_m=log.get("free_ahead_m"),
                    confidence=log["confidence"],
                    app=log.get("app", "unknown")
                )
                for log in logs_data
            ]
            session.bulk_save_objects(logs)
            session.commit()
            return len(logs)
        finally:
            session.close()

    def get_logs(
        self,
        client_id: str,
        session_id: Optional[str] = None,
        time_start: Optional[int] = None,
        time_end: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[LogRecord]:
        """
        Query log records with filters.

        Args:
            client_id: User identifier
            session_id: Optional session filter
            time_start: Unix timestamp start (inclusive)
            time_end: Unix timestamp end (exclusive)
            limit: Maximum number of records

        Returns:
            List of LogRecord objects
        """
        session = self.get_session()
        try:
            query = session.query(LogRecord).filter(LogRecord.client_id == client_id)

            if session_id:
                query = query.filter(LogRecord.session_id == session_id)
            if time_start is not None:
                query = query.filter(LogRecord.t >= time_start)
            if time_end is not None:
                query = query.filter(LogRecord.t < time_end)

            query = query.order_by(LogRecord.t.asc())

            if limit:
                query = query.limit(limit)

            return query.all()
        finally:
            session.close()

    def get_recent_logs(self, client_id: str, limit: int = 100) -> List[LogRecord]:
        """Get most recent logs for a client (for watchdog)."""
        session = self.get_session()
        try:
            return session.query(LogRecord)\
                .filter(LogRecord.client_id == client_id)\
                .order_by(LogRecord.t.desc())\
                .limit(limit)\
                .all()
        finally:
            session.close()

    # ========================================================================
    # USER INDICES
    # ========================================================================

    def save_index(self, client_id: str, index_data: dict, session_id: Optional[str] = None, time_start: Optional[int] = None, time_end: Optional[int] = None) -> UserIndex:
        """Save or update user index."""
        session = self.get_session()
        try:
            # Check if index exists
            query = session.query(UserIndex).filter(UserIndex.client_id == client_id)
            if session_id:
                query = query.filter(UserIndex.session_id == session_id)

            existing = query.first()

            if existing:
                # Update existing
                existing.index_data = index_data
                existing.time_start = time_start
                existing.time_end = time_end
                existing.updated_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(existing)
                return existing
            else:
                # Create new
                index = UserIndex(
                    client_id=client_id,
                    session_id=session_id,
                    time_start=time_start,
                    time_end=time_end,
                    index_data=index_data
                )
                session.add(index)
                session.commit()
                session.refresh(index)
                return index
        finally:
            session.close()

    def get_index(self, client_id: str, session_id: Optional[str] = None) -> Optional[dict]:
        """Retrieve cached user index."""
        session = self.get_session()
        try:
            query = session.query(UserIndex).filter(UserIndex.client_id == client_id)
            if session_id:
                query = query.filter(UserIndex.session_id == session_id)

            index = query.first()
            return index.index_data if index else None
        finally:
            session.close()

    # ========================================================================
    # ALERTS
    # ========================================================================

    def insert_alert(self, alert_data: dict) -> Alert:
        """Insert an alert record."""
        session = self.get_session()
        try:
            alert = Alert(
                alert_type=alert_data["alert_type"],
                client_id=alert_data["client_id"],
                contact_id=alert_data["contact_id"],
                t=alert_data["t"],
                rationale=alert_data.get("rationale"),
                payload=alert_data.get("payload")
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert
        finally:
            session.close()

    def get_recent_alerts(self, client_id: str, alert_type: Optional[str] = None, limit: int = 10) -> List[Alert]:
        """Get recent alerts for a client."""
        session = self.get_session()
        try:
            query = session.query(Alert).filter(Alert.client_id == client_id)
            if alert_type:
                query = query.filter(Alert.alert_type == alert_type)

            return query.order_by(Alert.created_at.desc()).limit(limit).all()
        finally:
            session.close()

    # ========================================================================
    # EMERGENCY CONTACTS
    # ========================================================================

    def add_emergency_contact(self, client_id: str, contact_id: str, contact_name: Optional[str] = None, contact_phone: Optional[str] = None, contact_email: Optional[str] = None) -> EmergencyContact:
        """Add or update emergency contact."""
        session = self.get_session()
        try:
            # Check if exists
            existing = session.query(EmergencyContact)\
                .filter(EmergencyContact.client_id == client_id)\
                .filter(EmergencyContact.contact_id == contact_id)\
                .first()

            if existing:
                # Update
                existing.authorized = 1
                if contact_name:
                    existing.contact_name = contact_name
                if contact_phone:
                    existing.contact_phone = contact_phone
                if contact_email:
                    existing.contact_email = contact_email
                session.commit()
                session.refresh(existing)
                return existing
            else:
                # Create new
                contact = EmergencyContact(
                    client_id=client_id,
                    contact_id=contact_id,
                    contact_name=contact_name,
                    contact_phone=contact_phone,
                    contact_email=contact_email
                )
                session.add(contact)
                session.commit()
                session.refresh(contact)
                return contact
        finally:
            session.close()

    def get_emergency_contacts(self, client_id: str) -> List[EmergencyContact]:
        """Get all authorized emergency contacts for a client."""
        session = self.get_session()
        try:
            return session.query(EmergencyContact)\
                .filter(EmergencyContact.client_id == client_id)\
                .filter(EmergencyContact.authorized == 1)\
                .all()
        finally:
            session.close()

    def is_authorized(self, requester_id: str, client_id: str) -> bool:
        """Check if requester is authorized to access client data."""
        session = self.get_session()
        try:
            contact = session.query(EmergencyContact)\
                .filter(EmergencyContact.client_id == client_id)\
                .filter(EmergencyContact.contact_id == requester_id)\
                .filter(EmergencyContact.authorized == 1)\
                .first()
            return contact is not None
        finally:
            session.close()


# ============================================================================
# GLOBAL DATABASE SERVICE INSTANCE
# ============================================================================

db_service = DatabaseService()


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_database():
    """Initialize database and create tables."""
    db_service.init_db()
    print("Database ready at:", DATABASE_URL)


if __name__ == "__main__":
    print("Initializing database...")
    init_database()
    print("\nDatabase structure:")
    print("  - log_records: Navigation logs from YOLO app")
    print("  - user_indices: Cached aggregations")
    print("  - alerts: Sent alerts history")
    print("  - emergency_contacts: Authorized contacts")
    print("\nDone!")
