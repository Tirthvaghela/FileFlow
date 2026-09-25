import { describe, expect, it } from "vitest";
import { applyRuleToDoc, FORM_TYPE_TO_RULE_TYPE, proposalFields } from "./ruleForm.js";

function baseDoc() {
  return {
    keyword_rules: [],
    extension_rules: {},
    regex_rules: [],
    content_keyword_rules: [],
    date_rules: [],
    large_file_threshold_mb: 500,
    large_file_folder: "Large Files",
    large_file_enabled: false,
  };
}

describe("applyRuleToDoc", () => {
  it("appends a keyword rule", () => {
    const result = applyRuleToDoc(baseDoc(), "keyword", { keyword: "invoice", destination: "Finance" });
    expect(result.keyword_rules).toEqual([{ keyword: "invoice", folder: "Finance" }]);
  });

  it("appends a content_keyword rule", () => {
    const result = applyRuleToDoc(baseDoc(), "content_keyword", { keyword: "GST", destination: "Finance" });
    expect(result.content_keyword_rules).toEqual([{ keyword: "GST", folder: "Finance" }]);
  });

  it("appends a regex rule", () => {
    const result = applyRuleToDoc(baseDoc(), "regex", { pattern: "^IMG_\\d+", destination: "Camera" });
    expect(result.regex_rules).toEqual([{ pattern: "^IMG_\\d+", folder: "Camera" }]);
  });

  it("appends a date rule", () => {
    const result = applyRuleToDoc(baseDoc(), "date", { olderThanDays: 30, destination: "Archive" });
    expect(result.date_rules).toEqual([{ older_than_days: 30, folder: "Archive" }]);
  });

  it("adds a normalized extension rule, prefixing the dot if missing", () => {
    const result = applyRuleToDoc(baseDoc(), "extension", { keyword: "pdf", destination: "Documents" });
    expect(result.extension_rules[".pdf"]).toBe("Documents");
  });

  it("does not double-prefix an extension that already has a dot", () => {
    const result = applyRuleToDoc(baseDoc(), "extension", { keyword: ".pdf", destination: "Documents" });
    expect(result.extension_rules[".pdf"]).toBe("Documents");
    expect(Object.keys(result.extension_rules)).toEqual([".pdf"]);
  });

  it("sets the large_file singleton fields directly, not as a list entry", () => {
    const result = applyRuleToDoc(baseDoc(), "large_file", { thresholdMb: 750, destination: "Huge" });
    expect(result.large_file_threshold_mb).toBe(750);
    expect(result.large_file_folder).toBe("Huge");
    expect(result.large_file_enabled).toBe(true);
  });

  it("does not mutate the original document", () => {
    const doc = baseDoc();
    applyRuleToDoc(doc, "keyword", { keyword: "invoice", destination: "Finance" });
    expect(doc.keyword_rules).toEqual([]);
  });

  it("returns the document unchanged for an unrecognized rule type", () => {
    const doc = baseDoc();
    const result = applyRuleToDoc(doc, "shell_command", { destination: "Anywhere" });
    expect(result).toEqual(doc);
  });
});

describe("proposalFields", () => {
  it("maps an AIRuleProposal-shaped object onto applyRuleToDoc's field names", () => {
    const proposal = {
      rule_type: "date",
      keyword: null,
      pattern: null,
      older_than_days: 45,
      threshold_mb: null,
      destination: "Archive",
    };

    expect(proposalFields(proposal)).toEqual({
      keyword: null,
      pattern: null,
      olderThanDays: 45,
      thresholdMb: null,
      destination: "Archive",
    });
  });
});

describe("FORM_TYPE_TO_RULE_TYPE", () => {
  it("maps every manual form condition type to a real rule_type", () => {
    expect(FORM_TYPE_TO_RULE_TYPE).toEqual({
      extension: "extension",
      keyword: "keyword",
      regex: "regex",
      content: "content_keyword",
      date: "date",
    });
  });
});
