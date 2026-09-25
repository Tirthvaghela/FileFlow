"""Thin LLM provider abstraction, shared by every AI-assisted feature in
FileFlow (currently the AI Rule Generator and AI Unclassified File
Suggestions).

This is a deliberately small seam rather than a generic multi-provider
framework: one function in (a system prompt + a user prompt), one parsed
JSON value out. Each feature gets its own thin wrapper below
(generate_rule_completion / generate_suggestion_completion) carrying its own
system prompt and its own expected top-level shape (dict vs list) -- but
there is exactly one place that actually talks to a provider over HTTP and
exactly one place that maps a provider/HTTP failure onto the typed
exceptions below. Every caller treats whatever this returns as completely
untrusted -- this module's only job is turning a prompt into *some* parsed
JSON value and translating every provider failure mode into one of the
exceptions below, never leaking a raw httpx/provider error up to a route.
"""

import json
import logging

import httpx

from config.settings import settings

logger = logging.getLogger("fileflow.ai")

ANTHROPIC_VERSION = "2023-06-01"
MAX_RESPONSE_TOKENS = 1024

# Keeps the model's job narrow and its output mechanical: FileFlow's actual
# supported rule types/fields (mirrors rules/classifier.py's real evaluation
# order and models/schemas.py's real KeywordRule/RegexRule/DateRule), the
# exact three response envelopes, and an explicit reminder that this is a
# proposal only -- never treated as ground truth, since
# services/ai_rule_service.py re-validates every field through those same
# real schemas regardless of what comes back here.
RULE_SYSTEM_PROMPT = """You turn a short natural-language request into a proposed FileFlow file-organization rule. You are NOT FileFlow's rule engine and you never execute anything -- you only propose a structured rule for a human to review and explicitly save. You have no access to the user's files, filesystem, or account data; you only see the text of their request.

FileFlow supports exactly these rule types -- never invent any other type:
- "keyword": move a file whose FILENAME contains a given word/phrase.
- "content_keyword": move a file whose CONTENTS contain a given word/phrase.
- "regex": move a file whose filename matches a regular expression.
- "extension": move every file with a given extension (e.g. ".pdf").
- "date": move a file older than a given number of days.
- "large_file": move a file larger than a given size threshold in MB.

If a request describes something none of these six types can express (e.g. "organize by how important a file looks", "sort by who sent it", "group similar files together"), it is unsupported -- do not approximate it with the closest type.

If a request is missing information needed to build a rule (no destination folder, or an ambiguous match condition such as "important documents" with no defined criterion), ask for clarification instead of guessing.

Respond with ONLY one JSON object, no other text, in exactly one of these three shapes:

1. Ready to propose:
{"status": "ready", "rule": {"rule_type": "keyword", "name": "Short human label", "keyword": "invoice", "destination": "Finance/Invoices"}}

Field meaning per rule_type (omit fields that don't apply to the chosen type):
- keyword / content_keyword: "keyword" (the word/phrase to match), "destination".
- regex: "pattern" (the regular expression), "destination".
- extension: "keyword" (the extension, e.g. ".pdf"), "destination".
- date: "older_than_days" (integer), "destination".
- large_file: "threshold_mb" (integer), "destination".
"destination" is always a plain relative folder path inside the user's own watch folder, e.g. "Finance/Invoices" or "Archive" -- never an absolute path, drive letter, UNC path (\\\\server\\share), or a path containing "..".

2. Needs clarification:
{"status": "needs_clarification", "message": "One sentence explaining what's missing.", "questions": ["Specific question 1", "Specific question 2"]}

3. Unsupported:
{"status": "unsupported", "message": "One sentence explaining this isn't a supported FileFlow condition, mentioning which of the six types above are available."}

Never wrap the JSON in markdown code fences. Never include commentary outside the JSON object."""

# Same "structured proposal only, never ground truth" contract as
# RULE_SYSTEM_PROMPT above, for AI Unclassified File Suggestions
# (services/ai_unclassified_service.py) -- this model never sees a file's
# contents or its real path, only safe metadata already scrubbed by the
# caller, and its output goes through the exact same per-type rule
# validation (services/ai_rule_service._validate_candidate) before a
# suggested_rule is ever shown as "ready".
SUGGESTION_SYSTEM_PROMPT = """You suggest what an unclassified computer file might be and where it could belong, for FileFlow (a file-organization tool). You are NOT deciding or executing anything -- your output is only a suggestion a human will review. You have no filesystem access and never see file contents; you only see the safe metadata provided below.

You will receive a JSON array of file GROUPS -- each one represents one or more files sharing a similar name pattern that FileFlow's rule engine could not classify. Each group has: group_index, filename (one representative file from the group), extension, size_bytes, and files_affected (how many files share this pattern).

Respond with ONLY a JSON array, one object per group, in the same order, in exactly this shape:

{"group_index": 0, "status": "ready", "suggested_category": "Invoices", "reason": ["Filename contains \\"invoice\\"", "PDF document"], "suggested_rule": {"rule_type": "keyword", "keyword": "invoice", "destination": "Finance/Invoices"}}

`status` must be exactly one of:
- "ready": a specific, defensible suggestion backed by concrete reasoning in the filename/extension/size given.
- "low_confidence": you have a guess, but it is weak and could easily be wrong -- still include suggested_category/reason/suggested_rule, but state the reasoning plainly as uncertain.
- "needs_clarification": the filename/extension/size alone do not provide enough information.
- "unsupported": no FileFlow rule type (filename keyword, file-content keyword, regex, extension, file age, file size) could express a rule for this kind of file.

Only include "suggested_rule" for "ready" or "low_confidence". Its fields follow FileFlow's own rule schema: rule_type ("keyword"|"content_keyword"|"regex"|"extension"|"date"|"large_file"), plus whichever of keyword/pattern/older_than_days/threshold_mb applies to that rule_type, plus destination (a plain relative folder path inside the user's own watch folder -- never an absolute path, drive letter, UNC path, or a path containing "..").

Never invent a numeric confidence percentage. Never fabricate a reason not actually supported by the filename/extension/size given -- if you don't have enough to go on, say so honestly via needs_clarification rather than forcing a category. Never wrap the JSON in markdown code fences. Never include commentary outside the JSON array."""

# Natural Language File Search (services/file_search_service.py): the AI's
# ONLY job is turning a search request into a structured SearchQuery
# (models/schemas.py) -- it never sees a single filename, path, or file
# metadata value, and its output is never treated as search results. The
# deterministic search engine (automation/file_ops.py, shared with the
# agent) is the only thing that ever decides which files actually match.
SEARCH_SYSTEM_PROMPT = """You turn a short natural-language file-search request into a structured search query for FileFlow (a file-organization tool). You are NOT the search engine -- you never see the user's actual files, filenames, folders, or any filesystem data, and you never decide which files match. You only see the text of their search request; a separate, deterministic step performs the real search from your structured query.

Respond with ONLY one JSON object, no other text, in exactly one of these three shapes:

1. Ready:
{"status": "ready", "query": { ... }}

"query" fields (omit any that don't apply -- never guess a value the request doesn't clearly support):
- "filename_contains": array of words/phrases that should appear in the FILENAME (not the folder path).
- "extension": array of file extensions, e.g. [".pdf"].
- "path_contains": array of words that should appear in the file's folder location, e.g. ["Finance"].
- "size_min_mb" / "size_max_mb": plain numbers, always in MEGABYTES, never bytes -- e.g. "larger than 10 MB" means size_min_mb: 10.
- "time_range": one of "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "older_than_days", "month_year", "after_date", "before_date". You never compute an actual date or figure out what today's date is -- you only pick which ONE of these concepts the request describes, and the backend computes the real boundary.
  - with "older_than_days": also set "time_range_days" (integer number of days).
  - with "month_year": also set "time_range_month" (1-12); only set "time_range_year" if the user named a specific year.
  - with "after_date" / "before_date": also set "time_range_date" as "YYYY-MM-DD", only if the user gave an explicit calendar date.
- "category_contains": a word describing the destination/category folder, e.g. "Finance".
- "rule_name_contains": a word describing which rule organizes/would organize the file.
- "unclassified_only": true only if the user is specifically asking about files with no matching rule.
- "duplicate_only": true only if the user is specifically asking about duplicate-content files.
- "sort_by": "modified_at" | "size_bytes" | "filename".
- "sort_order": "asc" | "desc".
- "limit": integer, only if the user gave an explicit count (e.g. "top 10" -> 10).

FileFlow Search is METADATA ONLY -- it never reads file contents, never uses OCR, and has no idea what is written inside any document. If the request needs understanding a file's actual content or meaning (e.g. "about machine learning", "my most important files", "the one I was thinking about yesterday"), it is unsupported.

If the request is missing information you would otherwise have to guess (an undefined date range, an undefined notion like "important"), ask for clarification instead of guessing.

2. Needs clarification:
{"status": "needs_clarification", "message": "One sentence explaining what's missing.", "questions": ["Specific question 1"]}

3. Unsupported:
{"status": "unsupported", "message": "One sentence explaining this isn't a supported FileFlow search concept."}

Never wrap the JSON in markdown code fences. Never include commentary outside the JSON object. Never include a "results", "files", "interpretation", or "path" field of your own -- you never produce search results or a real filesystem path, only the structured query above."""


class AIProviderError(Exception):
    """Base for every AI-provider failure -- callers catch this (or a more
    specific subclass below) and translate it into a short, user-safe
    message. The real cause is logged here, never returned to the client."""


class AIProviderUnavailable(AIProviderError):
    """Provider unreachable, timed out, or returned a server error."""


class AIProviderAuthError(AIProviderError):
    """The configured API key was rejected -- never the caller's fault."""


class AIProviderRateLimited(AIProviderError):
    """The provider itself rate-limited this request."""


class AIProviderMalformedResponse(AIProviderError):
    """Provider returned 200 but not the JSON shape expected."""


def _request_completion_anthropic(system_prompt: str, prompt: str) -> httpx.Response:
    return httpx.post(
        settings.AI_PROVIDER_BASE_URL,
        headers={
            "x-api-key": settings.AI_PROVIDER_API_KEY or "",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": settings.AI_PROVIDER_MODEL,
            "max_tokens": MAX_RESPONSE_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
    )


def _extract_text_anthropic(body: dict) -> str:
    return body["content"][0]["text"]


def _request_completion_gemini(system_prompt: str, prompt: str) -> httpx.Response:
    # The key rides in a header (x-goog-api-key), not the URL's query
    # string, for the same reason Anthropic's goes in a header -- a query
    # string is far more likely to end up copied into logs, browser
    # history, or a proxy's access log than a header is.
    url = f"{settings.GEMINI_API_BASE_URL}/{settings.AI_PROVIDER_MODEL}:generateContent"
    return httpx.post(
        url,
        headers={
            "x-goog-api-key": settings.AI_PROVIDER_API_KEY or "",
            "content-type": "application/json",
        },
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": MAX_RESPONSE_TOKENS,
                # Gemini honors this directly (unlike Anthropic, which has
                # no equivalent knob here) -- one more layer against a
                # malformed/non-JSON reply, on top of the json.loads() both
                # providers still go through below.
                "responseMimeType": "application/json",
            },
        },
        timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
    )


def _extract_text_gemini(body: dict) -> str:
    return body["candidates"][0]["content"]["parts"][0]["text"]


# Adding a provider means adding one entry here (a request-builder + a
# text-extractor) -- nothing else in this module, and nothing in any
# feature's own service (ai_rule_service.py, ai_unclassified_service.py),
# needs to know which provider is active.
_PROVIDERS = {
    "anthropic": (_request_completion_anthropic, _extract_text_anthropic),
    "gemini": (_request_completion_gemini, _extract_text_gemini),
}


def _request_completion(system_prompt: str, prompt: str) -> httpx.Response:
    """The one network call this module makes -- isolated in its own
    function so tests can monkeypatch it directly (same convention as every
    other single-seam function in this codebase) instead of mocking httpx
    internals or making a real network call."""
    request_fn, _ = _PROVIDERS.get(settings.AI_PROVIDER, _PROVIDERS["anthropic"])
    return request_fn(system_prompt, prompt)


def _extract_text(body: dict) -> str:
    _, extract_fn = _PROVIDERS.get(settings.AI_PROVIDER, _PROVIDERS["anthropic"])
    return extract_fn(body)


def _generate_completion(system_prompt: str, prompt: str):
    """Shared plumbing behind every feature-specific wrapper below: sends
    `prompt` to the configured provider under `system_prompt` and returns
    whatever JSON value the model's text parses to (a dict or a list,
    depending on which wrapper is calling) -- untrusted either way, and
    each wrapper is responsible for checking it's the shape that feature
    actually expects. Raises one of the AIProviderError subclasses above
    for every failure mode (missing config, timeout, connection failure,
    non-2xx status, unparseable body) instead of letting a raw
    httpx/provider exception escape to a route."""
    if not settings.AI_PROVIDER_API_KEY:
        raise AIProviderUnavailable("AI service is not configured.")

    try:
        response = _request_completion(system_prompt, prompt)
    except httpx.TimeoutException as exc:
        raise AIProviderUnavailable("AI service timed out.") from exc
    except httpx.HTTPError as exc:
        raise AIProviderUnavailable("AI service is unreachable.") from exc

    if response.status_code in (401, 403):
        logger.error("AI provider authentication failed (status %s).", response.status_code)
        raise AIProviderAuthError("AI service authentication failed.")
    if response.status_code == 429:
        raise AIProviderRateLimited("AI service rate limit exceeded.")
    if response.status_code >= 500:
        raise AIProviderUnavailable("AI service is temporarily unavailable.")
    if response.status_code != 200:
        logger.warning(
            "Unexpected AI provider status %s: %s", response.status_code, response.text[:500]
        )
        raise AIProviderUnavailable("AI service returned an unexpected response.")

    try:
        body = response.json()
        text = _extract_text(body)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AIProviderMalformedResponse(
            "AI service returned an unexpected response shape."
        ) from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIProviderMalformedResponse("AI service response wasn't valid JSON.") from exc


def generate_rule_completion(prompt: str) -> dict:
    """AI Rule Generator (services/ai_rule_service.py): returns the parsed
    JSON object -- untrusted output the caller must validate field-by-field
    before treating any of it as a real rule."""
    parsed = _generate_completion(RULE_SYSTEM_PROMPT, prompt)
    if not isinstance(parsed, dict):
        raise AIProviderMalformedResponse("AI service response wasn't a JSON object.")
    return parsed


def generate_suggestion_completion(prompt: str) -> list:
    """AI Unclassified File Suggestions (services/ai_unclassified_service.py):
    returns the parsed JSON array (one entry per file group) -- untrusted
    output the caller must validate entry-by-entry before treating any of
    it as a real suggestion."""
    parsed = _generate_completion(SUGGESTION_SYSTEM_PROMPT, prompt)
    if not isinstance(parsed, list):
        raise AIProviderMalformedResponse("AI service response wasn't a JSON array.")
    return parsed


def generate_search_completion(prompt: str) -> dict:
    """Natural Language File Search (services/file_search_service.py):
    returns the parsed JSON object -- untrusted output the caller must
    validate through models.schemas.SearchQuery before it can ever be used
    to filter a single real file."""
    parsed = _generate_completion(SEARCH_SYSTEM_PROMPT, prompt)
    if not isinstance(parsed, dict):
        raise AIProviderMalformedResponse("AI service response wasn't a JSON object.")
    return parsed
