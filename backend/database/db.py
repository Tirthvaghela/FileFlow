from pymongo import MongoClient, ReturnDocument

from config.settings import settings

client = MongoClient(settings.MONGO_URI)
db = client[settings.MONGO_DB_NAME]


def get_db():
    return db


def next_id(database, name: str) -> int:
    """Atomic sequential integer id, so documents keep the same int `id`
    semantics the old SQLite autoincrement primary keys had (ordering,
    JWT `sub`, path params, Pydantic `id: int` fields all stay unchanged)."""
    doc = database.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


def insert_with_id(database, collection_name: str, doc: dict) -> dict:
    """Insert `doc`, stamping it with an app-generated sequential int id
    on both `_id` (Mongo's real key) and `id` (so plain dict access, e.g.
    from Pydantic's from_attributes mapping lookup, finds it too)."""
    new_id = next_id(database, collection_name)
    doc["_id"] = new_id
    doc["id"] = new_id
    database[collection_name].insert_one(doc)
    return doc


def init_db() -> None:
    db.users.create_index("email", unique=True)
    # Every query filters by user_id first, then either sorts by _id desc
    # (routes.py, report_service.py) or range-filters on timestamp
    # (stats_service.py, report_service.py) -- no query touches timestamp
    # without user_id, so a compound index covers both shapes without
    # needing a standalone single-field timestamp index.
    db.activity_log.create_index([("user_id", 1), ("_id", -1)])
    db.activity_log.create_index([("user_id", 1), ("timestamp", 1)])
