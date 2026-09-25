"""AI Rule Generator: natural language -> structured rule PROPOSAL.

AI SUGGESTS. THE EXISTING RULE ENGINE DECIDES. THE USER CONFIRMS.

generate_rule_proposal() below is the only entry point routes.py calls. It
never writes to the database and never touches the filesystem -- it returns
an AIRuleGenerateResponse for the frontend to render, and saving (if the
user chooses to) happens entirely through the pre-existing PUT /api/rules
path, unchanged by this feature.

Everything services.ai_provider.generate_rule_completion() returns is
treated as untrusted input, exactly like a value submitted by an end user:
every field of a "ready" proposal is re-validated through the *same*
per-type models (KeywordRule/RegexRule/DateRule) and the *same* destination
check (rules.classifier.is_within_watch_folder) a manually-created rule is
subject to -- there is no separate, weaker validation path for AI output.
"""

import logging
import re
from pathlib import Path

from pydantic import ValidationError

from models.schemas import (
    AIRuleGenerateResponse,
    AIRuleProposal,
    DateRule,
    KeywordRule,
    RegexRule,
)
from rules.classifier import is_within_watch_folder
from services.ai_provider import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderMalformedResponse,
    AIProviderRateLimited,
    AIProviderUnavailable,
    generate_rule_completion,
)

logger = logging.getLogger("fileflow.ai")

# A rule request is a short sentence, not a document -- this also bounds
# what's ever sent to the provider (Phase 15/16: "excessively long prompt").
MAX_PROMPT_LENGTH = 500

SUPPORTED_RULE_TYPES = {"keyword", "content_keyword", "regex", "extension", "date", "large_file"}

# Loose sanity check on an AI-proposed extension -- not a path, so this
# isn't a traversal vector, but a stray "/" or ".." here would still be a
# sign the model misunderstood the request rather than a real extension.
_EXTENSION_RE = re.compile(r"^\.[A-Za-z0-9]{1,15}$")

UNAVAILABLE_MESSAGE = "AI service is temporarily unavailable. Please try again shortly."
UNSUPPORTED_MESSAGE = (
    "I can't create a supported FileFlow rule from that request. FileFlow can match on "
    "filename keyword, file content keyword, regex pattern, extension, file age, or file size."
)
MALFORMED_MESSAGE = "The request could not be converted into a supported FileFlow rule."


def generate_rule_proposal(prompt: str, watch_root: Path) -> AIRuleGenerateResponse:
    prompt = (prompt or "").strip()
    if not prompt:
        return AIRuleGenerateResponse(
            status="invalid", message="Please describe the rule you want to create."
        )
    if len(prompt) > MAX_PROMPT_LENGTH:
        return AIRuleGenerateResponse(
            status="invalid",
            message=f"That description is too long (max {MAX_PROMPT_LENGTH} characters).",
        )

    try:
        raw = generate_rule_completion(prompt)
    except AIProviderRateLimited:
        return AIRuleGenerateResponse(
            status="error", message="AI service is busy right now. Please try again in a moment."
        )
    except AIProviderAuthError:
        # Never surfaced to the client -- a misconfigured/revoked key is an
        # operator problem, not something the requester did wrong or needs
        # (or is entitled) to know the specifics of.
        logger.error("AI provider authentication failed while generating a rule proposal.")
        return AIRuleGenerateResponse(status="error", message=UNAVAILABLE_MESSAGE)
    except (AIProviderUnavailable, AIProviderMalformedResponse, AIProviderError) as exc:
        logger.warning("AI provider failure while generating a rule proposal: %s", exc)
        return AIRuleGenerateResponse(status="error", message=UNAVAILABLE_MESSAGE)

    if not isinstance(raw, dict):
        return AIRuleGenerateResponse(status="error", message=MALFORMED_MESSAGE)

    ai_status = raw.get("status")

    if ai_status == "unsupported":
        message = raw.get("message")
        return AIRuleGenerateResponse(
            status="unsupported",
            message=message if isinstance(message, str) and message.strip() else UNSUPPORTED_MESSAGE,
        )

    if ai_status == "needs_clarification":
        message = raw.get("message")
        raw_questions = raw.get("questions")
        questions = (
            [q for q in raw_questions if isinstance(q, str) and q.strip()]
            if isinstance(raw_questions, list)
            else []
        )
        return AIRuleGenerateResponse(
            status="needs_clarification",
            message=message
            if isinstance(message, str) and message.strip()
            else "I need a bit more detail to create this rule.",
            questions=questions,
        )

    if ai_status != "ready":
        # Anything else -- missing status, a status we don't recognize --
        # is a malformed response, not a supported outcome to guess at.
        return AIRuleGenerateResponse(status="error", message=MALFORMED_MESSAGE)

    try:
        candidate = AIRuleProposal.model_validate(raw.get("rule"))
    except ValidationError:
        return AIRuleGenerateResponse(status="error", message=MALFORMED_MESSAGE)

    return _validate_candidate(candidate, watch_root)


def _validate_candidate(candidate: AIRuleProposal, watch_root: Path) -> AIRuleGenerateResponse:
    """The actual gate: every field the AI proposed is checked against the
    real rule schemas/constraints before this can ever become `status:
    "ready"`. Anything that would be rejected if a user had typed it into
    the manual rule form is rejected here the same way."""
    if candidate.rule_type not in SUPPORTED_RULE_TYPES:
        return AIRuleGenerateResponse(status="unsupported", message=UNSUPPORTED_MESSAGE)

    destination = (candidate.destination or "").strip()
    if not destination:
        return AIRuleGenerateResponse(
            status="invalid", message="Please describe the destination folder."
        )
    # Same containment check classify_file_explained() applies to every
    # rule's folder at match time (rules/classifier.py) -- applied here too,
    # up front, so an AI-proposed destination outside the watch folder is
    # rejected as a proposal rather than silently saved as a rule that can
    # never actually match anything.
    if not is_within_watch_folder(destination, watch_root):
        return AIRuleGenerateResponse(
            status="invalid",
            message="The suggested destination must be a folder inside your watch folder.",
        )

    try:
        if candidate.rule_type in ("keyword", "content_keyword"):
            keyword = (candidate.keyword or "").strip()
            if not keyword:
                return AIRuleGenerateResponse(
                    status="invalid",
                    message="Please describe what to match in the filename or file content.",
                )
            KeywordRule(keyword=keyword, folder=destination)
            candidate.keyword = keyword
        elif candidate.rule_type == "regex":
            pattern = (candidate.pattern or "").strip()
            if not pattern:
                return AIRuleGenerateResponse(
                    status="invalid", message="Please describe the pattern to match."
                )
            RegexRule(pattern=pattern, folder=destination)
            candidate.pattern = pattern
        elif candidate.rule_type == "date":
            if candidate.older_than_days is None or candidate.older_than_days < 0:
                return AIRuleGenerateResponse(
                    status="invalid",
                    message="Please specify how many days old a file should be.",
                )
            DateRule(older_than_days=candidate.older_than_days, folder=destination)
        elif candidate.rule_type == "extension":
            ext = (candidate.keyword or "").strip().lower()
            if ext and not ext.startswith("."):
                ext = f".{ext}"
            if not ext or not _EXTENSION_RE.match(ext):
                return AIRuleGenerateResponse(
                    status="invalid", message="Please specify a valid file extension."
                )
            candidate.keyword = ext
        elif candidate.rule_type == "large_file":
            if candidate.threshold_mb is None or candidate.threshold_mb <= 0:
                return AIRuleGenerateResponse(
                    status="invalid",
                    message="Please specify a file size threshold greater than 0 MB.",
                )
    except ValidationError as exc:
        return AIRuleGenerateResponse(status="invalid", message=_first_error_message(exc))

    candidate.name = (candidate.name or "").strip() or _default_name(candidate)
    candidate.destination = destination
    return AIRuleGenerateResponse(status="ready", proposal=candidate)


def _first_error_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        return str(errors[0].get("msg") or "That rule isn't valid.")
    return "That rule isn't valid."


def _default_name(candidate: AIRuleProposal) -> str:
    if candidate.rule_type in ("keyword", "content_keyword") and candidate.keyword:
        return candidate.keyword.title()
    if candidate.rule_type == "regex" and candidate.pattern:
        return f"Pattern {candidate.pattern}"
    if candidate.rule_type == "extension" and candidate.keyword:
        return f"{candidate.keyword} files"
    if candidate.rule_type == "date" and candidate.older_than_days is not None:
        return f"Older than {candidate.older_than_days} days"
    if candidate.rule_type == "large_file" and candidate.threshold_mb is not None:
        return f"Larger than {candidate.threshold_mb} MB"
    return "New rule"
