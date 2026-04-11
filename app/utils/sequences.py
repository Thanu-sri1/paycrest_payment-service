
import re
from pymongo import ReturnDocument
from ..database.mongo import get_db
from ..core.config import settings

def _format_ifsc(seq: int) -> str:
    base = settings.DEFAULT_IFSC
    match = re.match(r"^(.*?)(\d+)$", base)
    if match:
        prefix, number = match.group(1), match.group(2)
        width = len(number)
    else:
        prefix, width = base, 4
    return f"{prefix}{seq:0{width}d}"

async def next_account_number() -> int:
    db = await get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": "account_number"},
        [
            {
                "$set": {
                    "seq": {
                        "$add": [
                            {"$ifNull": ["$seq", 999999999]},
                            1,
                        ]
                    }
                }
            }
        ],
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])  # starts at 1000000000


async def next_customer_id() -> int:
    db = await get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": "customer_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])  # starts at 1


async def next_loan_id() -> int:
    db = await get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": "loan_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])  # starts at 1


async def next_transaction_id() -> int:
    db = await get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": "transaction_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])  # starts at 1


async def next_ifsc_code() -> str:
    db = await get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": "ifsc_code"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return _format_ifsc(int(doc["seq"]))
