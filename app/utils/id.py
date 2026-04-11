
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail=f"Invalid id: {id_str}")


def loan_id_filter(id_str: str):
    """Return a MongoDB filter for a loan identifier.

    Accepts either a numeric loan id (stored in `loan_id`) or an ObjectId string for `_id`.
    """
    if id_str is None:
        raise HTTPException(status_code=404, detail="Missing loan id")
    # try numeric loan id first
    try:
        lid = int(id_str)
        return {"loan_id": lid}
    except (ValueError, TypeError):
        # fallback to ObjectId
        try:
            oid = ObjectId(id_str)
            return {"_id": oid}
        except (InvalidId, TypeError):
            raise HTTPException(status_code=404, detail=f"Invalid id: {id_str}")


def user_id_filter(id_str: str):
    """Return a MongoDB filter for a user identifier.

    Users in this project typically use a numeric `_id` (same as `customer_id`),
    but we also accept an ObjectId string for flexibility.
    """
    if id_str is None:
        raise HTTPException(status_code=404, detail="Missing user id")
    try:
        uid = int(id_str)
        return {"_id": uid}
    except (ValueError, TypeError):
        try:
            oid = ObjectId(id_str)
            return {"_id": oid}
        except (InvalidId, TypeError):
            raise HTTPException(status_code=404, detail=f"Invalid id: {id_str}")
