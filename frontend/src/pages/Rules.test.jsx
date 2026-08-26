import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Rules from "./Rules.jsx";

const baseRules = {
  categories: { Documents: [".pdf"] },
  extension_rules: { ".py": "Python Projects" },
  disabled_extension_rules: {},
  keyword_rules: [{ keyword: "invoice", folder: "Finance Folder" }],
  disabled_keyword_rules: [],
  regex_rules: [],
  disabled_regex_rules: [],
  date_rules: [],
  disabled_date_rules: [],
  content_keyword_rules: [],
  disabled_content_keyword_rules: [],
  large_file_threshold_mb: 500,
  large_file_folder: "Large Files",
  large_file_enabled: true,
  archive_after_days: 30,
  archive_folder: "Archive",
  default_category: "Others",
  auto_organize_unknown_extensions: true,
  enable_timestamp_rename: false,
  timestamp_rename_categories: [],
};

vi.mock("../services/api.js", () => ({
  previewRule: vi.fn().mockResolvedValue({ matched_count: 0, by_category: [], samples: [] }),
  simulateRules: vi.fn(),
  // Pulled in transitively by the shared Header component -- not part of
  // what this file is testing, just what's needed to mount the real page.
  getLogs: vi.fn().mockResolvedValue([]),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
}));

const mockSaveRules = vi.fn();
vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({ rules: baseRules, saveRules: mockSaveRules }),
}));

function renderRules() {
  return render(
    <MemoryRouter>
      <Rules />
    </MemoryRouter>,
  );
}

function fillAndSubmitRegexRule(pattern, folder) {
  fireEvent.change(screen.getByLabelText(/condition type/i), { target: { value: "regex" } });
  fireEvent.change(screen.getByLabelText(/regex pattern/i), { target: { value: pattern } });
  fireEvent.change(screen.getByLabelText(/destination folder/i), { target: { value: folder } });
  fireEvent.click(screen.getByRole("button", { name: /add rule/i }));
}

describe("Rules page: add-rule failure handling", () => {
  it("preserves the typed pattern and folder when the backend rejects the rule", async () => {
    // Simulates a real backend 422 -- e.g. the ReDoS-shaped-pattern
    // rejection or an uncompilable regex added in the rule-engine audit.
    mockSaveRules.mockRejectedValueOnce({ response: { status: 422 } });
    renderRules();

    fillAndSubmitRegexRule("(a+)+$", "Camera");

    await waitFor(() => expect(screen.getByText(/failed to save/i)).toBeInTheDocument());

    // The condition-type dropdown must still say "regex" -- if the whole
    // form silently reset to its "extension" default despite the save
    // failing, the "Regex pattern" label below wouldn't even exist anymore.
    expect(screen.getByLabelText(/condition type/i).value).toBe("regex");
    expect(screen.getByLabelText(/regex pattern/i).value).toBe("(a+)+$");
    expect(screen.getByLabelText(/destination folder/i).value).toBe("Camera");
  });

  it("clears the form after a successful add", async () => {
    mockSaveRules.mockResolvedValueOnce({ ...baseRules });
    renderRules();

    fillAndSubmitRegexRule("^IMG_\\d+", "Camera");

    await waitFor(() => expect(screen.getByText(/^saved$/i)).toBeInTheDocument());

    // A successful add resets the whole form back to its default, including
    // the condition-type dropdown -- "Regex pattern" reverts to "Match" and
    // the destination folder is empty again.
    expect(screen.getByLabelText(/condition type/i).value).toBe("extension");
    expect(screen.getByLabelText(/^match$/i).value).toBe("");
    expect(screen.getByLabelText(/destination folder/i).value).toBe("");
  });
});
