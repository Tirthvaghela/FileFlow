import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

const mockGenerateAIRule = vi.fn();
const mockCheckRuleConflicts = vi.fn().mockResolvedValue({
  conflicts: [],
  total: 0,
  info: 0,
  warnings: 0,
  high: 0,
  rules_checked: 0,
  truncated: false,
});
vi.mock("../services/api.js", () => ({
  previewRule: vi.fn().mockResolvedValue({ matched_count: 0, by_category: [], samples: [] }),
  simulateRules: vi.fn(),
  generateAIRule: (...args) => mockGenerateAIRule(...args),
  checkRuleConflicts: (...args) => mockCheckRuleConflicts(...args),
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

describe("Rules page: AI Rule Generator", () => {
  const READY_PROPOSAL = {
    status: "ready",
    proposal: {
      rule_type: "keyword",
      name: "GST Invoices",
      keyword: "gstinvoice",
      destination: "Finance/Invoices",
    },
  };

  async function openAIDialog() {
    renderRules();
    fireEvent.click(screen.getByRole("button", { name: /create with ai/i }));
  }

  async function generate(text) {
    fireEvent.change(screen.getByPlaceholderText(/put invoices containing gst/i), {
      target: { value: text },
    });
    fireEvent.click(screen.getByRole("button", { name: /^generate rule$/i }));
  }

  beforeEach(() => {
    mockGenerateAIRule.mockReset();
    mockSaveRules.mockReset();
  });

  it("opens the dialog and lets the user enter a natural-language request", async () => {
    await openAIDialog();

    expect(screen.getByText(/create rule with ai/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/put invoices containing gst/i)).toBeInTheDocument();
  });

  it("shows a loading state while generating, then renders the proposal", async () => {
    let resolveGenerate;
    mockGenerateAIRule.mockReturnValue(
      new Promise((resolve) => {
        resolveGenerate = resolve;
      }),
    );
    await openAIDialog();

    await generate("Put GST invoices into Finance/Invoices");
    expect(screen.getByText(/interpreting your request/i)).toBeInTheDocument();

    resolveGenerate(READY_PROPOSAL);
    await screen.findByText("GST Invoices");
    expect(screen.getAllByText(/Finance\/Invoices/).length).toBeGreaterThan(0);
  });

  it("does not save anything just by generating a proposal", async () => {
    mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
    await openAIDialog();

    await generate("Put GST invoices into Finance/Invoices");
    await screen.findByText("GST Invoices");

    expect(mockSaveRules).not.toHaveBeenCalled();
  });

  it("Reject closes the dialog without saving", async () => {
    mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
    await openAIDialog();
    await generate("Put GST invoices into Finance/Invoices");
    await screen.findByText("GST Invoices");

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));

    await waitFor(() => expect(screen.queryByText(/create rule with ai/i)).not.toBeInTheDocument());
    expect(mockSaveRules).not.toHaveBeenCalled();
  });

  it("Save Rule persists the proposal through the existing rule-save path", async () => {
    mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
    mockSaveRules.mockResolvedValue({ ...baseRules });
    await openAIDialog();
    await generate("Put GST invoices into Finance/Invoices");
    await screen.findByText("GST Invoices");

    fireEvent.click(screen.getByRole("button", { name: /^save rule$/i }));

    await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
    // saveRules() (the exact same function the manual "Add rule" button
    // calls) is invoked with an updater built from the current rules doc --
    // confirms the proposal was folded into keyword_rules, not saved
    // through some separate mechanism.
    const updater = mockSaveRules.mock.calls[0][0];
    const result = updater(baseRules);
    expect(result.keyword_rules).toContainEqual({ keyword: "gstinvoice", folder: "Finance/Invoices" });
  });

  it("Edit populates the existing manual rule form instead of saving directly", async () => {
    mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
    await openAIDialog();
    await generate("Put GST invoices into Finance/Invoices");
    await screen.findByText("GST Invoices");

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));

    // The AI dialog is gone, and the pre-existing "New rule" form (right
    // panel) now carries the proposal's fields -- nothing has been saved
    // yet, the user still has to press the existing "Add rule" button.
    await waitFor(() => expect(screen.queryByText(/create rule with ai/i)).not.toBeInTheDocument());
    expect(screen.getByLabelText(/condition type/i).value).toBe("keyword");
    expect(screen.getByLabelText(/^match$/i).value).toBe("gstinvoice");
    expect(screen.getByLabelText(/destination folder/i).value).toBe("Finance/Invoices");
    expect(mockSaveRules).not.toHaveBeenCalled();

    mockSaveRules.mockResolvedValueOnce({ ...baseRules });
    fireEvent.click(screen.getByRole("button", { name: /add rule/i }));
    await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
  });

  it("shows an unsupported-request message without a proposal or save option", async () => {
    mockGenerateAIRule.mockResolvedValue({
      status: "unsupported",
      message: "I can't create a supported FileFlow rule from that request.",
    });
    await openAIDialog();

    await generate("Sort files by how important they look");

    expect(await screen.findByText(/can't create a supported fileflow rule/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save rule$/i })).not.toBeInTheDocument();
  });

  it("shows a clarification message with follow-up questions", async () => {
    mockGenerateAIRule.mockResolvedValue({
      status: "needs_clarification",
      message: "I need a bit more detail.",
      questions: ["What counts as important?", "Where should these go?"],
    });
    await openAIDialog();

    await generate("Put important documents somewhere safe");

    expect(await screen.findByText(/i need a bit more detail/i)).toBeInTheDocument();
    expect(screen.getByText("What counts as important?")).toBeInTheDocument();
  });

  it("shows an error when the AI service call itself fails", async () => {
    mockGenerateAIRule.mockRejectedValue({ response: { status: 500 } });
    await openAIDialog();

    await generate("Put GST invoices into Finance/Invoices");

    expect(await screen.findByText(/couldn't reach the ai service/i)).toBeInTheDocument();
  });

  it("does not fire a second request from a rapid double-click on Generate", async () => {
    let resolveGenerate;
    mockGenerateAIRule.mockReturnValue(
      new Promise((resolve) => {
        resolveGenerate = resolve;
      }),
    );
    await openAIDialog();

    fireEvent.change(screen.getByPlaceholderText(/put invoices containing gst/i), {
      target: { value: "Put GST invoices into Finance/Invoices" },
    });
    const generateButton = screen.getByRole("button", { name: /^generate rule$/i });
    fireEvent.click(generateButton);
    fireEvent.click(generateButton);
    fireEvent.click(generateButton);

    resolveGenerate(READY_PROPOSAL);
    await screen.findByText("GST Invoices");

    expect(mockGenerateAIRule).toHaveBeenCalledTimes(1);
  });

  it("never calls anything organize-related while generating or reviewing a proposal", async () => {
    // Rules.jsx has no organize-existing import at all -- this asserts the
    // one relevant call this test *can* observe (saveRules) stays untouched
    // by generation/review, i.e. nothing here can trigger a save/organize
    // side effect on its own.
    mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
    await openAIDialog();
    await generate("Put GST invoices into Finance/Invoices");
    await screen.findByText("GST Invoices");

    expect(mockSaveRules).not.toHaveBeenCalled();
  });
});

describe("Rules page: rule conflict detector", () => {
  const WARNING_CONFLICT = {
    severity: "warning",
    type: "precedence_overlap",
    rules: [
      { rule_type: "keyword", description: 'Keyword "invoice"', destination: "Finance/Invoices" },
      { rule_type: "extension", description: 'Extension ".pdf"', destination: "Documents/PDF" },
    ],
    example: { filename: "invoice.pdf", destination: "Finance/Invoices", winning_rule: 'Keyword "invoice"' },
    message: 'Both rules can match invoice.pdf. Keyword rules are evaluated before extension rules.',
  };

  beforeEach(() => {
    mockSaveRules.mockReset();
    mockCheckRuleConflicts.mockReset();
    mockCheckRuleConflicts.mockResolvedValue({
      conflicts: [],
      total: 0,
      info: 0,
      warnings: 0,
      high: 0,
      rules_checked: 7,
      truncated: false,
    });
  });

  describe("standing Rule Analysis panel", () => {
    it("shows a clean result when nothing overlaps", async () => {
      renderRules();

      fireEvent.click(screen.getByRole("button", { name: /check conflicts/i }));

      expect(await screen.findByText(/no potential conflicts found/i)).toBeInTheDocument();
      expect(screen.getByText(/7 rules checked/i)).toBeInTheDocument();
    });

    it("lists a detected conflict with its example and reasoning", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      renderRules();

      fireEvent.click(screen.getByRole("button", { name: /check conflicts/i }));

      expect(await screen.findByText(/1 potential overlap/i)).toBeInTheDocument();
      expect(screen.getByText(/Keyword "invoice"\s+vs\.\s+Extension "\.pdf"/)).toBeInTheDocument();
      expect(screen.getByText("invoice.pdf")).toBeInTheDocument();
    });

    it("surfaces a request failure distinctly", async () => {
      mockCheckRuleConflicts.mockRejectedValueOnce(new Error("network"));
      renderRules();

      fireEvent.click(screen.getByRole("button", { name: /check conflicts/i }));

      expect(await screen.findByText(/couldn't check rule conflicts/i)).toBeInTheDocument();
    });

    it("never saves anything just by checking conflicts", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      renderRules();

      fireEvent.click(screen.getByRole("button", { name: /check conflicts/i }));
      await screen.findByText(/1 potential overlap/i);

      expect(mockSaveRules).not.toHaveBeenCalled();
    });
  });

  describe("pre-save gate on the manual Add rule form", () => {
    it("saves normally when no conflict is found", async () => {
      mockSaveRules.mockResolvedValueOnce({ ...baseRules });
      renderRules();

      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");

      await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
      expect(screen.queryByText(/rule conflict detected/i)).not.toBeInTheDocument();
    });

    it("shows the warning dialog instead of saving immediately when a conflict is found", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      renderRules();

      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");

      expect(await screen.findByText(/rule conflict detected/i)).toBeInTheDocument();
      expect(mockSaveRules).not.toHaveBeenCalled();
    });

    it("Back & Edit closes the dialog without saving, keeping the form filled", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      renderRules();
      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");
      await screen.findByText(/rule conflict detected/i);

      fireEvent.click(screen.getByRole("button", { name: /back & edit/i }));

      await waitFor(() => expect(screen.queryByText(/rule conflict detected/i)).not.toBeInTheDocument());
      expect(mockSaveRules).not.toHaveBeenCalled();
      expect(screen.getByLabelText(/regex pattern/i).value).toBe("^IMG_\\d+");
    });

    it("Save Anyway saves through the exact same save path", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      mockSaveRules.mockResolvedValueOnce({ ...baseRules });
      renderRules();
      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");
      await screen.findByText(/rule conflict detected/i);

      fireEvent.click(screen.getByRole("button", { name: /save anyway/i }));

      await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
      const updater = mockSaveRules.mock.calls[0][0];
      const result = updater(baseRules);
      expect(result.regex_rules).toContainEqual({ pattern: "^IMG_\\d+", folder: "Camera" });
      await waitFor(() => expect(screen.queryByText(/rule conflict detected/i)).not.toBeInTheDocument());
    });

    it("only info-severity findings never open the warning dialog", async () => {
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [{ ...WARNING_CONFLICT, severity: "info", type: "overlap" }],
        total: 1,
        info: 1,
        warnings: 0,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      mockSaveRules.mockResolvedValueOnce({ ...baseRules });
      renderRules();

      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");

      await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
      expect(screen.queryByText(/rule conflict detected/i)).not.toBeInTheDocument();
    });

    it("a failed conflict check never blocks saving", async () => {
      mockCheckRuleConflicts.mockRejectedValueOnce(new Error("network"));
      mockSaveRules.mockResolvedValueOnce({ ...baseRules });
      renderRules();

      fillAndSubmitRegexRule("^IMG_\\d+", "Camera");

      await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
    });
  });

  describe("pre-save gate on the AI Rule Generator's Save Rule", () => {
    const READY_PROPOSAL = {
      status: "ready",
      proposal: {
        rule_type: "keyword",
        name: "GST Invoices",
        keyword: "gstinvoice",
        destination: "Finance/Invoices",
      },
    };

    async function openAndGenerate() {
      renderRules();
      fireEvent.click(screen.getByRole("button", { name: /create with ai/i }));
      fireEvent.change(screen.getByPlaceholderText(/put invoices containing gst/i), {
        target: { value: "Put GST invoices into Finance/Invoices" },
      });
      fireEvent.click(screen.getByRole("button", { name: /^generate rule$/i }));
      await screen.findByText("GST Invoices");
    }

    it("shows the warning dialog before saving an AI proposal that conflicts", async () => {
      mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      await openAndGenerate();

      fireEvent.click(screen.getByRole("button", { name: /^save rule$/i }));

      expect(await screen.findByText(/rule conflict detected/i)).toBeInTheDocument();
      expect(mockSaveRules).not.toHaveBeenCalled();
    });

    it("Save Anyway from the AI flow saves through the same path and closes the AI dialog too", async () => {
      mockGenerateAIRule.mockResolvedValue(READY_PROPOSAL);
      mockCheckRuleConflicts.mockResolvedValueOnce({
        conflicts: [WARNING_CONFLICT],
        total: 1,
        info: 0,
        warnings: 1,
        high: 0,
        rules_checked: 2,
        truncated: false,
      });
      mockSaveRules.mockResolvedValueOnce({ ...baseRules });
      await openAndGenerate();
      fireEvent.click(screen.getByRole("button", { name: /^save rule$/i }));
      await screen.findByText(/rule conflict detected/i);

      fireEvent.click(screen.getByRole("button", { name: /save anyway/i }));

      await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(screen.queryByText(/create rule with ai/i)).not.toBeInTheDocument());
    });
  });
});
