from datetime import datetime, date, timezone
from bson import ObjectId
from typing import Any


def normalize_value(v: Any) -> Any:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        # Persist API datetime strings as explicit UTC (with trailing Z) so frontend
        # does not misread naive timestamps as local time.
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        return v.isoformat().replace("+00:00", "Z")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return normalize_doc(v)
    if isinstance(v, list):
        return [normalize_value(x) for x in v]
    return v


def normalize_doc(doc: dict) -> dict:
    return {str(k): normalize_value(v) for k, v in doc.items()}
