// The one place that knows how each supported condition type maps into the
// rules document -- shared by the manual "Add rule" form (Rules.jsx), the
// AI Rule Generator's Save/Check-impact (Rules.jsx), and AI Unclassified
// File Suggestions' "Create Rule" (Dashboard.jsx). All three ultimately
// just propose the same shape a human typing into the form would, so there
// is exactly one implementation of "what does adding this type of rule
// actually change" rather than three independent ones that could drift.
export function applyRuleToDoc(current, ruleType, fields) {
  const { keyword, pattern, olderThanDays, thresholdMb, destination } = fields;
  switch (ruleType) {
    case "extension": {
      const ext = keyword.startsWith(".") ? keyword : `.${keyword}`;
      return { ...current, extension_rules: { ...current.extension_rules, [ext]: destination } };
    }
    case "keyword":
      return { ...current, keyword_rules: [...current.keyword_rules, { keyword, folder: destination }] };
    case "content_keyword":
      return {
        ...current,
        content_keyword_rules: [...(current.content_keyword_rules || []), { keyword, folder: destination }],
      };
    case "regex":
      return { ...current, regex_rules: [...(current.regex_rules || []), { pattern, folder: destination }] };
    case "date":
      return {
        ...current,
        date_rules: [...(current.date_rules || []), { older_than_days: olderThanDays, folder: destination }],
      };
    case "large_file":
      return {
        ...current,
        large_file_threshold_mb: thresholdMb,
        large_file_folder: destination,
        large_file_enabled: true,
      };
    default:
      return current;
  }
}

// Maps the manual "New rule" form's own condition-type vocabulary
// ("content" instead of "content_keyword", no "large_file" option since
// that's a singleton toggle, not a list) onto applyRuleToDoc's rule_type
// vocabulary, which instead matches AIRuleProposal.rule_type exactly
// (services/ai_rule_service.py, backend). The two vocabularies differ only
// because the manual form predates the AI features and already shipped
// with its own naming.
export const FORM_TYPE_TO_RULE_TYPE = {
  extension: "extension",
  keyword: "keyword",
  regex: "regex",
  content: "content_keyword",
  date: "date",
};

// A proposal (AIRuleProposal from either /api/rules/ai-generate or
// /api/unclassified/suggestions' suggested_rule -- identically shaped) into
// applyRuleToDoc's generic `fields` argument.
export function proposalFields(proposal) {
  return {
    keyword: proposal.keyword,
    pattern: proposal.pattern,
    olderThanDays: proposal.older_than_days,
    thresholdMb: proposal.threshold_mb,
    destination: proposal.destination,
  };
}
