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


def init_db(database=None) -> None:
    """Takes an explicit `database` (defaulting to the module-level `db`)
    so tests can apply the exact same indexes to their own disposable
    per-test database -- without that, index-dependent bugs (a unique
    index that's wrong in a way that only shows up against real data) are
    invisible to the test suite, which is exactly how the client_ref
    index bug below shipped unnoticed in the first place."""
    database = db if database is None else database
    database.users.create_index("email", unique=True)
    # Sparse: only users with an outstanding "forgot password" request have
    # this field at all, and reset-password looks it up by exact hash.
    database.users.create_index("reset_token_hash", sparse=True)
    # Every query filters by user_id first, then either sorts by _id desc
    # (routes.py, report_service.py) or range-filters on timestamp
    # (stats_service.py, report_service.py) -- no query touches timestamp
    # without user_id, so a compound index covers both shapes without
    # needing a standalone single-field timestamp index.
    database.activity_log.create_index([("user_id", 1), ("_id", -1)])
    database.activity_log.create_index([("user_id", 1), ("timestamp", 1)])
    # Agent polls GET /api/agent/commands filtered on exactly these two
    # fields, ordered by _id -- same compound-index shape as activity_log.
    database.agent_commands.create_index([("user_id", 1), ("status", 1)])
    # Lets POST /api/agent/activity recognize a retried report (agent
    # outbox.py's flush_outbox() delivering the same client_ref again
    # after a response got lost) instead of inserting a duplicate row.
    # partialFilterExpression, not sparse: sparse on a COMPOUND index only
    # skips a document when *every* indexed field is missing -- since
    # user_id is never missing, a plain sparse index here would treat
    # every plain (non-agent) log as client_ref=null and collide with any
    # other one for the same user the moment a second existed (verified
    # directly -- this crashed startup with a duplicate-key error on real
    # data). A partial index filters per-document on the condition given,
    # correctly limiting uniqueness to rows that actually carry the field.
    database.activity_log.create_index(
        [("user_id", 1), ("client_ref", 1)],
        unique=True,
        partialFilterExpression={"client_ref": {"$exists": True}},
    )
