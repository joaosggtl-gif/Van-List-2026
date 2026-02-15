from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(
    db: Session,
    user: User,
    action: str,
    entity_type: str = None,
    entity_id: int = None,
    details: str = None,
):
    """Record an audit log entry."""
    entry = AuditLog(
        user_id=user.id,
        username=user.username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    db.flush()
    return entry
