
from datetime import datetime, timedelta


def next_month_date(from_date: datetime | None = None) -> datetime:
    base = from_date or datetime.utcnow()
    # naive next month approximation: add 30 days
    return base + timedelta(days=30)
