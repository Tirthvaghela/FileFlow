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
    client_ref = kwargs.pop("client_ref", None)
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
    # Omitted entirely (not set to None) for a non-agent-reported log --
    # the activity_log unique index on (user_id, client_ref) is sparse,
    # which only excludes documents where the field is truly ABSENT, not
    # ones where it's explicitly null. Setting it to None here for every
    # locally-organized file would make Mongo see them all as duplicates
    # of each other the moment a second one exists for the same user.
    if client_ref is not None:
        doc["client_ref"] = client_ref
    return doc


def new_user(**kwargs) -> Document:
    doc = Document(
        email=kwargs.pop("email"),
        password_hash=kwargs.pop("password_hash"),
        watch_folder=kwargs.pop("watch_folder"),
        created_at=kwargs.pop("created_at", None) or utcnow(),
        onboarding_completed=kwargs.pop("onboarding_completed", False),
        agent_token_version=kwargs.pop("agent_token_version", 0),
    )
    if kwargs:
        raise TypeError(f"new_user() got unexpected fields: {sorted(kwargs)}")
    return doc
