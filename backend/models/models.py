from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(dict):
    """Thin dict wrapper giving attribute-style access on top of a Mongo
    document (log.category, log.id, log.undone = True), so call-sites that
    read/mutate a fetched document don't need to change just because the
    storage engine did -- only construction/query call-sites do."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


# Allowed values for ActivityLog.action.
ACTIVITY_LOG_ACTIONS = (
    "moved",
    "renamed_and_moved",
    "replaced",
    "duplicate_skipped",
    "archived",
    "reclassified",
)


def new_activity_log(**kwargs) -> Document:
    doc = Document(
        user_id=kwargs.pop("user_id"),
        timestamp=kwargs.pop("timestamp", None) or utcnow(),
        original_filename=kwargs.pop("original_filename"),
        final_filename=kwargs.pop("final_filename"),
        source_path=kwargs.pop("source_path"),
        destination_path=kwargs.pop("destination_path", None),
        category=kwargs.pop("category"),
        action=kwargs.pop("action"),
        file_size=kwargs.pop("file_size", 0),
        file_hash=kwargs.pop("file_hash", None),
        undone=kwargs.pop("undone", False),
    )
    if kwargs:
        raise TypeError(f"new_activity_log() got unexpected fields: {sorted(kwargs)}")
    return doc


def new_user(**kwargs) -> Document:
    doc = Document(
        email=kwargs.pop("email"),
        password_hash=kwargs.pop("password_hash"),
        watch_folder=kwargs.pop("watch_folder"),
        created_at=kwargs.pop("created_at", None) or utcnow(),
    )
    if kwargs:
        raise TypeError(f"new_user() got unexpected fields: {sorted(kwargs)}")
    return doc
