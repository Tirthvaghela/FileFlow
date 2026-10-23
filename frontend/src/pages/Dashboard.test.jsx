import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard.jsx";

const mockGetStats = vi.fn();
const mockGetCategories = vi.fn();
const mockGetWeeklyReports = vi.fn();
const mockOrganizeExistingFiles = vi.fn();
const mockPreviewOrganizeExisting = vi.fn();
const mockReclassifyLog = vi.fn();
const mockUndoLastOperation = vi.fn();
const mockGetAgentCommands = vi.fn();
const mockGetUnclassifiedSuggestions = vi.fn();
const mockAnalyzeDuplicates = vi.fn();
const mockSearchFiles = vi.fn();
const mockGetOrganizationHealth = vi.fn();
const mockSaveRules = vi.fn();

const DEFAULT_HEALTH = {
  generated_at: "2026-01-01T00:00:00Z",
  agent_connected: false,
  files: {
    status: "available",
    message: null,
    scanned: 0,
    classified: 0,
    unclassified: 0,
    errors: 0,
    classification_coverage_percent: null,
  },
  duplicates: { status: "available", message: null, groups: 0, duplicate_files: 0, potential_redundant_bytes: 0 },
  rules: {
    status: "available",
    message: null,
    active: 0,
    disabled: 0,
    conflicts_total: 0,
    conflicts_high: 0,
    conflicts_warning: 0,
    redundant_rules: 0,
  },
  activity: {
    status: "available",
    message: null,
    last_24_hours: { organized: 0, skipped: 0 },
    last_7_days: { organized: 0, skipped: 0 },
    last_30_days: { organized: 0, skipped: 0 },
  },
};
// Every Dashboard test mounts the real Dashboard component, which now
// fetches health unconditionally on mount -- a harmless default here so
// tests unrelated to Feature 8 don't each have to stub it themselves.
mockGetOrganizationHealth.mockResolvedValue(DEFAULT_HEALTH);

// Lets one test render the Active rules panel with a chosen keyword_rules list.
const { rulesOverride } = vi.hoisted(() => ({ rulesOverride: { keywordRules: [] } }));

const { logs } = vi.hoisted(() => ({
  logs: [
    {
      id: 1,
      final_filename: "report.pdf",
      original_filename: "report.pdf",
      category: "Documents",
      action: "moved",
      destination_path: "C:/watch/Documents/report.pdf",
      timestamp: "2026-01-01T08:00:00Z",
      undone: false,
    },
  ],
}));

const READY_PREVIEW_ITEM = {
  filename: "invoice_august.pdf",
  source_path: "C:/watch/invoice_august.pdf",
  destination_path: "C:/watch/Documents/Invoices/invoice_august.pdf",
  category: "Documents/Invoices",
  action: "moved",
  status: "ready",
  explanation: {
    match_type: "keyword",
    matched_value: "invoice",
    destination: "Documents/Invoices",
    rule_name: 'Keyword "invoice"',
    priority: 1,
  },
  error: null,
};

vi.mock("../services/api.js", () => ({
  getStats: (...args) => mockGetStats(...args),
  getCategories: (...args) => mockGetCategories(...args),
  getWeeklyReports: (...args) => mockGetWeeklyReports(...args),
  organizeExistingFiles: (...args) => mockOrganizeExistingFiles(...args),
  previewOrganizeExisting: (...args) => mockPreviewOrganizeExisting(...args),
  reclassifyLog: (...args) => mockReclassifyLog(...args),
  undoLastOperation: (...args) => mockUndoLastOperation(...args),
  getAgentCommands: (...args) => mockGetAgentCommands(...args),
  getUnclassifiedSuggestions: (...args) => mockGetUnclassifiedSuggestions(...args),
  analyzeDuplicates: (...args) => mockAnalyzeDuplicates(...args),
  searchFiles: (...args) => mockSearchFiles(...args),
  getOrganizationHealth: (...args) => mockGetOrganizationHealth(...args),
  getLogs: vi.fn().mockResolvedValue(logs),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
}));

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({
    rules: {
      realtime_monitoring_enabled: true,
      keyword_rules: rulesOverride.keywordRules,
      extension_rules: {},
      large_file_enabled: false,
      categories: { Documents: [".pdf"], Archive: [] },
    },
    saveRules: (...args) => mockSaveRules(...args),
  }),
}));

vi.mock("../context/AuthContext.jsx", () => ({
  useAuth: () => ({ user: { watch_folder: "C:/watch" } }),
}));

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

describe("Dashboard mutation failure handling", () => {
  it("shows an error when the existing-files sweep fails, instead of failing silently", async () => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      ready: 1,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [READY_PREVIEW_ITEM],
    });
    mockOrganizeExistingFiles.mockRejectedValueOnce({ response: { status: 500 } });
    renderDashboard();

    fireEvent.click(
      await screen.findByRole("button", { name: /preview the plan/i }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /organize 1 file/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/couldn't organize existing files/i),
      ).toBeInTheDocument(),
    );
  });
});

describe("Dashboard's organization preview flow", () => {
  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockPreviewOrganizeExisting.mockReset();
    mockOrganizeExistingFiles.mockReset();
  });

  async function openPreview() {
    renderDashboard();
    fireEvent.click(
      await screen.findByRole("button", { name: /preview the plan/i }),
    );
  }

  it("opens the preview dialog and shows what a click on the button will do", async () => {
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      ready: 1,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [READY_PREVIEW_ITEM],
    });

    await openPreview();

    expect(await screen.findByText("Organization Preview")).toBeInTheDocument();
    expect(await screen.findByText("invoice_august.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Documents\/Invoices/)).toBeInTheDocument();
    expect(screen.getByText(/Keyword "invoice"/)).toBeInTheDocument();
  });

  it("shows a loading state while the preview is being computed", async () => {
    let resolvePreview;
    mockPreviewOrganizeExisting.mockReturnValue(
      new Promise((resolve) => {
        resolvePreview = resolve;
      }),
    );

    await openPreview();

    expect(screen.getByText("Organization Preview")).toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    resolvePreview({ queued: false, command_id: null, total: 0, ready: 0, duplicates: 0, no_match: 0, errors: 0, items: [] });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
  });

  it("shows an error when the preview itself fails to load", async () => {
    mockPreviewOrganizeExisting.mockRejectedValue({ response: { status: 500 } });

    await openPreview();

    expect(await screen.findByText(/couldn't preview existing files/i)).toBeInTheDocument();
  });

  it("cancel closes the dialog without organizing anything", async () => {
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      ready: 1,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [READY_PREVIEW_ITEM],
    });

    await openPreview();
    await screen.findByText("invoice_august.pdf");
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByText("Organization Preview")).not.toBeInTheDocument());
    expect(mockOrganizeExistingFiles).not.toHaveBeenCalled();
  });

  it("confirming calls the real organize-existing endpoint, not a fabricated result from the preview", async () => {
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      ready: 1,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [READY_PREVIEW_ITEM],
    });
    mockOrganizeExistingFiles.mockResolvedValue({ scanned: 1, organized: 1, duplicates: 0, errors: 0 });

    await openPreview();
    fireEvent.click(await screen.findByRole("button", { name: /organize 1 file/i }));

    await waitFor(() => expect(mockOrganizeExistingFiles).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Organization Preview")).not.toBeInTheDocument());
  });

  it("shows an empty preview state when there is nothing to organize", async () => {
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 0,
      ready: 0,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [],
    });

    await openPreview();

    expect(await screen.findByText(/nothing to organize/i)).toBeInTheDocument();
  });

  it("disables the confirm button while organizing is in progress and does not fire twice from a rapid double-click", async () => {
    mockPreviewOrganizeExisting.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      ready: 1,
      duplicates: 0,
      no_match: 0,
      errors: 0,
      items: [READY_PREVIEW_ITEM],
    });
    let resolveOrganize;
    mockOrganizeExistingFiles.mockReturnValue(
      new Promise((resolve) => {
        resolveOrganize = resolve;
      }),
    );

    await openPreview();
    const confirmButton = await screen.findByRole("button", { name: /organize 1 file/i });
    fireEvent.click(confirmButton);
    await waitFor(() => expect(screen.getByRole("button", { name: /organizing/i })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /organizing/i }));
    fireEvent.click(screen.getByRole("button", { name: /organizing/i }));

    resolveOrganize({ scanned: 1, organized: 1, duplicates: 0, errors: 0 });
    await waitFor(() => expect(screen.queryByText("Organization Preview")).not.toBeInTheDocument());

    expect(mockOrganizeExistingFiles).toHaveBeenCalledTimes(1);
  });
});

const READY_SUGGESTION = {
  group_key: "mystery",
  file_names: ["mystery_file.xyz"],
  files_affected: 1,
  suggestion_status: "ready",
  suggested_category: "Invoices",
  suggested_destination: "Finance/Invoices",
  reason: ['Filename contains "invoice"'],
  suggested_rule: {
    rule_type: "keyword",
    name: "Invoices",
    keyword: "invoice",
    pattern: null,
    older_than_days: null,
    threshold_mb: null,
    destination: "Finance/Invoices",
  },
  message: null,
};

describe("Dashboard's AI Unclassified File Suggestions flow", () => {
  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockGetUnclassifiedSuggestions.mockReset();
    mockSaveRules.mockReset();
    mockOrganizeExistingFiles.mockReset();
  });

  // The entry point is the "Needs you" item, shown whenever health reports
  // unclassified files.
  async function openSuggestions() {
    mockGetOrganizationHealth.mockResolvedValue({
      ...DEFAULT_HEALTH,
      files: { ...DEFAULT_HEALTH.files, unclassified: 3 },
    });
    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: /unclassified files/i }));
  }

  it("opens the dialog and shows a suggestion", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      command_id: null,
      total: 1,
      unclassified: 1,
      suggestions: [READY_SUGGESTION],
      batch_limited: false,
      message: null,
    });

    await openSuggestions();

    expect(await screen.findByText("AI Suggestions")).toBeInTheDocument();
    expect(await screen.findByText("mystery_file.xyz")).toBeInTheDocument();
    expect(screen.getByText(/Finance\/Invoices/)).toBeInTheDocument();
  });

  it("shows a loading state while suggestions are being generated", async () => {
    let resolveIt;
    mockGetUnclassifiedSuggestions.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );

    await openSuggestions();

    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    resolveIt({ queued: false, total: 0, unclassified: 0, suggestions: [], batch_limited: false, message: null });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
  });

  it("shows an empty state when nothing is unclassified", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 3,
      unclassified: 0,
      suggestions: [],
      batch_limited: false,
      message: null,
    });

    await openSuggestions();

    expect(await screen.findByText(/nothing unclassified right now/i)).toBeInTheDocument();
  });

  it("shows an error when the request itself fails", async () => {
    mockGetUnclassifiedSuggestions.mockRejectedValue({ response: { status: 500 } });

    await openSuggestions();

    expect(await screen.findByText(/couldn't get ai suggestions/i)).toBeInTheDocument();
  });

  it("shows a whole-batch provider failure message distinctly", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 1,
      unclassified: 1,
      suggestions: [],
      batch_limited: false,
      message: "AI service is temporarily unavailable. Please try again shortly.",
    });

    await openSuggestions();

    expect(await screen.findByText(/ai service is temporarily unavailable/i)).toBeInTheDocument();
  });

  it("Create Rule saves through the real saveRules pipeline, not a fabricated result", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 1,
      unclassified: 1,
      suggestions: [READY_SUGGESTION],
      batch_limited: false,
      message: null,
    });
    mockSaveRules.mockResolvedValue({});

    await openSuggestions();
    fireEvent.click(await screen.findByRole("button", { name: /create rule/i }));

    await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
    const updater = mockSaveRules.mock.calls[0][0];
    const result = updater({ keyword_rules: [] });
    expect(result.keyword_rules).toContainEqual({ keyword: "invoice", folder: "Finance/Invoices" });
  });

  it("a suggestion is removed from the list after Create Rule succeeds", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 1,
      unclassified: 1,
      suggestions: [READY_SUGGESTION],
      batch_limited: false,
      message: null,
    });
    mockSaveRules.mockResolvedValue({});

    await openSuggestions();
    await screen.findByText("mystery_file.xyz");
    fireEvent.click(screen.getByRole("button", { name: /create rule/i }));

    await waitFor(() => expect(screen.queryByText("mystery_file.xyz")).not.toBeInTheDocument());
  });

  it("Ignore dismisses a suggestion without saving anything", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 1,
      unclassified: 1,
      suggestions: [READY_SUGGESTION],
      batch_limited: false,
      message: null,
    });

    await openSuggestions();
    await screen.findByText("mystery_file.xyz");
    fireEvent.click(screen.getByRole("button", { name: /^ignore$/i }));

    await waitFor(() => expect(screen.queryByText("mystery_file.xyz")).not.toBeInTheDocument());
    expect(mockSaveRules).not.toHaveBeenCalled();
  });

  it("never calls organize-existing at any point in the suggestion flow", async () => {
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: false,
      total: 1,
      unclassified: 1,
      suggestions: [READY_SUGGESTION],
      batch_limited: false,
      message: null,
    });
    mockSaveRules.mockResolvedValue({});

    await openSuggestions();
    fireEvent.click(await screen.findByRole("button", { name: /create rule/i }));
    await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));

    expect(mockOrganizeExistingFiles).not.toHaveBeenCalled();
  });

  it("does not fire a second request from rapid repeated clicks", async () => {
    let resolveIt;
    mockGetUnclassifiedSuggestions.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );
    renderDashboard();
    const button = await screen.findByRole("button", { name: /get ai suggestions/i });

    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    resolveIt({ queued: false, total: 0, unclassified: 0, suggestions: [], batch_limited: false, message: null });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(mockGetUnclassifiedSuggestions).toHaveBeenCalledTimes(1);
  });

  it("agent-connected: shows the waiting-for-agent state instead of a fabricated local result", async () => {
    // The full poll-until-done cycle (same 2s-interval pollForAgentPreview
    // pattern Organization Preview already uses) isn't re-exercised at
    // this level either -- see OrganizePreviewDialog's own tests for that
    // precedent. This confirms the one thing that's new here: a queued
    // response correctly shows "waiting for agent", not an empty/local
    // "nothing unclassified" result the backend never actually computed.
    mockGetUnclassifiedSuggestions.mockResolvedValue({
      queued: true,
      command_id: 42,
      total: 0,
      unclassified: 0,
      suggestions: [],
      batch_limited: false,
      message: null,
    });
    mockGetAgentCommands.mockResolvedValue([]); // never completes -- still polling

    await openSuggestions();

    expect(await screen.findByText(/waiting for your agent/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing unclassified right now/i)).not.toBeInTheDocument();
    expect(mockGetUnclassifiedSuggestions).toHaveBeenCalledTimes(1);

    // Cancels the still-running poll loop (real setTimeout underneath) so
    // it doesn't keep calling setState -- and therefore firing act()
    // warnings, or mocks other tests don't expect -- well past this test's
    // own lifetime.
    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
  });
});

describe("Dashboard's Duplicate Files flow", () => {
  const ONE_GROUP_RESULT = {
    queued: false,
    command_id: null,
    total_files_scanned: 3,
    duplicate_groups: 1,
    duplicate_files: 2,
    potential_redundant_bytes: 2446680,
    files_with_errors: 0,
    groups: [
      {
        group_id: "abc123def456",
        duplicate_type: "exact_content_duplicate",
        file_count: 2,
        total_size_bytes: 4893360,
        potential_redundant_bytes: 2446680,
        files: [
          {
            filename: "invoice.pdf",
            relative_path: "Finance/invoice.pdf",
            size_bytes: 2446680,
            modified_at: "2026-01-10T00:00:00Z",
            sha256: "a".repeat(64),
          },
          {
            filename: "invoice (1).pdf",
            relative_path: "Downloads/invoice (1).pdf",
            size_bytes: 2446680,
            modified_at: "2026-01-12T00:00:00Z",
            sha256: "a".repeat(64),
          },
        ],
      },
    ],
    groups_returned: 1,
    truncated: false,
  };

  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockAnalyzeDuplicates.mockReset();
    mockOrganizeExistingFiles.mockReset();
    mockSaveRules.mockReset();
  });

  async function openDuplicates() {
    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: /find duplicate files/i }));
  }

  it("opens the dialog and shows the entry point", async () => {
    renderDashboard();
    expect(await screen.findByRole("button", { name: /find duplicate files/i })).toBeInTheDocument();
  });

  it("shows the summary and a group after analysis", async () => {
    mockAnalyzeDuplicates.mockResolvedValue(ONE_GROUP_RESULT);

    await openDuplicates();

    expect(await screen.findByText("Duplicate Files")).toBeInTheDocument();
    expect(await screen.findByText(/1 duplicate group/i)).toBeInTheDocument();
    expect(screen.getByText("Duplicate Group #1")).toBeInTheDocument();
    expect(screen.getByText("invoice.pdf")).toBeInTheDocument();
  });

  it("shows a loading state while analyzing", async () => {
    let resolveIt;
    mockAnalyzeDuplicates.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );

    await openDuplicates();

    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    resolveIt({
      queued: false,
      total_files_scanned: 0,
      duplicate_groups: 0,
      duplicate_files: 0,
      potential_redundant_bytes: 0,
      files_with_errors: 0,
      groups: [],
      groups_returned: 0,
      truncated: false,
    });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
  });

  it("shows an empty state when nothing is duplicated", async () => {
    mockAnalyzeDuplicates.mockResolvedValue({
      queued: false,
      total_files_scanned: 5,
      duplicate_groups: 0,
      duplicate_files: 0,
      potential_redundant_bytes: 0,
      files_with_errors: 0,
      groups: [],
      groups_returned: 0,
      truncated: false,
    });

    await openDuplicates();

    expect(await screen.findByText(/no duplicate files found/i)).toBeInTheDocument();
  });

  it("shows an error when the request itself fails", async () => {
    mockAnalyzeDuplicates.mockRejectedValue({ response: { status: 500 } });

    await openDuplicates();

    expect(await screen.findByText(/couldn't check for duplicate files/i)).toBeInTheDocument();
  });

  it("Review Group opens the detail view with all files and the no-deletion confirmation", async () => {
    mockAnalyzeDuplicates.mockResolvedValue(ONE_GROUP_RESULT);

    await openDuplicates();
    fireEvent.click(await screen.findByRole("button", { name: /review group/i }));

    // Both the summary card and the stacked detail dialog show "Duplicate
    // Group #1" -- assert the detail dialog's own content instead.
    expect(await screen.findByText(/no files have been deleted/i)).toBeInTheDocument();
    expect(screen.getAllByText("invoice.pdf").length).toBeGreaterThan(0);
    expect(screen.getAllByText("invoice (1).pdf").length).toBeGreaterThan(0);
  });

  it("never calls organize-existing or saveRules at any point in the duplicate flow", async () => {
    mockAnalyzeDuplicates.mockResolvedValue(ONE_GROUP_RESULT);

    await openDuplicates();
    fireEvent.click(await screen.findByRole("button", { name: /review group/i }));
    await screen.findByText(/no files have been deleted/i);

    expect(mockOrganizeExistingFiles).not.toHaveBeenCalled();
    expect(mockSaveRules).not.toHaveBeenCalled();
  });

  it("Refresh re-runs the analysis", async () => {
    mockAnalyzeDuplicates.mockResolvedValue(ONE_GROUP_RESULT);

    await openDuplicates();
    await screen.findByText("Duplicate Group #1");
    fireEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

    await waitFor(() => expect(mockAnalyzeDuplicates).toHaveBeenCalledTimes(2));
  });

  it("does not fire a second request from rapid repeated clicks", async () => {
    let resolveIt;
    mockAnalyzeDuplicates.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );
    renderDashboard();
    const button = await screen.findByRole("button", { name: /find duplicate files/i });

    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    resolveIt({
      queued: false,
      total_files_scanned: 0,
      duplicate_groups: 0,
      duplicate_files: 0,
      potential_redundant_bytes: 0,
      files_with_errors: 0,
      groups: [],
      groups_returned: 0,
      truncated: false,
    });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(mockAnalyzeDuplicates).toHaveBeenCalledTimes(1);
  });

  it("agent-connected: shows the waiting-for-agent state instead of a fabricated local result", async () => {
    mockAnalyzeDuplicates.mockResolvedValue({
      queued: true,
      command_id: 42,
      total_files_scanned: 0,
      duplicate_groups: 0,
      duplicate_files: 0,
      potential_redundant_bytes: 0,
      files_with_errors: 0,
      groups: [],
      groups_returned: 0,
      truncated: false,
    });
    mockGetAgentCommands.mockResolvedValue([]); // never completes -- still polling

    await openDuplicates();

    expect(await screen.findByText(/waiting for your agent/i)).toBeInTheDocument();
    expect(screen.queryByText(/no duplicate files found/i)).not.toBeInTheDocument();
    expect(mockAnalyzeDuplicates).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
  });
});

describe("Dashboard's Natural Language File Search flow", () => {
  const READY_RESULT = {
    status: "ready",
    message: null,
    questions: [],
    interpretation: ['Filename contains "invoice"', "Extension is .pdf"],
    queued: false,
    command_id: null,
    total_files_scanned: 5,
    files_with_errors: 0,
    total_matches: 1,
    returned: 1,
    truncated: false,
    results: [
      {
        filename: "invoice_august.pdf",
        relative_path: "Finance/invoice_august.pdf",
        extension: ".pdf",
        size_bytes: 2446680,
        modified_at: "2026-08-18T00:00:00Z",
        category: "Finance",
        match_reasons: ['Filename contains "invoice"', "Extension is .pdf"],
      },
    ],
  };

  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockSearchFiles.mockReset();
    mockOrganizeExistingFiles.mockReset();
    mockSaveRules.mockReset();
  });

  async function openSearch() {
    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: /search your files/i }));
  }

  function typeAndSearch(text) {
    fireEvent.change(screen.getByPlaceholderText(/find pdf invoices from august/i), {
      target: { value: text },
    });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));
  }

  it("opens the dialog and shows the entry point", async () => {
    renderDashboard();
    expect(await screen.findByRole("button", { name: /search your files/i })).toBeInTheDocument();
  });

  it("running a search shows the interpretation and results", async () => {
    mockSearchFiles.mockResolvedValue(READY_RESULT);

    await openSearch();
    typeAndSearch("find pdf invoices from august");

    expect(await screen.findByText("invoice_august.pdf")).toBeInTheDocument();
    expect(screen.getByText(/search interpretation/i)).toBeInTheDocument();
  });

  it("shows a loading state while searching", async () => {
    let resolveIt;
    mockSearchFiles.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );

    await openSearch();
    typeAndSearch("find invoices");

    expect(screen.getAllByText(/searching…/i).length).toBeGreaterThan(0);

    resolveIt({ ...READY_RESULT, total_matches: 0, returned: 0, results: [] });
    await waitFor(() => expect(screen.queryAllByText(/searching…/i).length).toBe(0));
  });

  it("shows an empty result state", async () => {
    mockSearchFiles.mockResolvedValue({ ...READY_RESULT, total_matches: 0, returned: 0, results: [] });

    await openSearch();
    typeAndSearch("find nonexistent files");

    expect(await screen.findByText(/no files matched your search/i)).toBeInTheDocument();
  });

  it("shows an unsupported state", async () => {
    mockSearchFiles.mockResolvedValue({
      status: "unsupported",
      message: "FileFlow Search doesn't read file contents yet.",
      questions: [],
      interpretation: [],
    });

    await openSearch();
    typeAndSearch("find files about machine learning");

    expect(await screen.findByText(/doesn't read file contents yet/i)).toBeInTheDocument();
  });

  it("shows a request-level error", async () => {
    mockSearchFiles.mockRejectedValue({ response: { status: 500 } });

    await openSearch();
    typeAndSearch("find invoices");

    expect(await screen.findByText(/couldn't search your files/i)).toBeInTheDocument();
  });

  it("Clear Search resets the prompt and results", async () => {
    mockSearchFiles.mockResolvedValue(READY_RESULT);

    await openSearch();
    typeAndSearch("find pdf invoices from august");
    await screen.findByText("invoice_august.pdf");

    fireEvent.click(screen.getByRole("button", { name: /clear search/i }));

    expect(screen.queryByText("invoice_august.pdf")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/find pdf invoices from august/i).value).toBe("");
  });

  it("never calls organize-existing or saveRules at any point in the search flow", async () => {
    mockSearchFiles.mockResolvedValue(READY_RESULT);

    await openSearch();
    typeAndSearch("find pdf invoices from august");
    await screen.findByText("invoice_august.pdf");

    expect(mockOrganizeExistingFiles).not.toHaveBeenCalled();
    expect(mockSaveRules).not.toHaveBeenCalled();
  });

  it("does not fire a second request from rapid repeated clicks", async () => {
    let resolveIt;
    mockSearchFiles.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );
    await openSearch();
    fireEvent.change(screen.getByPlaceholderText(/find pdf invoices from august/i), {
      target: { value: "find invoices" },
    });
    const button = screen.getByRole("button", { name: /^search$/i });

    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    resolveIt({ ...READY_RESULT, total_matches: 0, returned: 0, results: [] });
    await waitFor(() => expect(screen.queryAllByText(/searching…/i).length).toBe(0));

    expect(mockSearchFiles).toHaveBeenCalledTimes(1);
  });

  it("does not expose an absolute filesystem path in results", async () => {
    mockSearchFiles.mockResolvedValue(READY_RESULT);

    await openSearch();
    typeAndSearch("find pdf invoices from august");
    await screen.findByText("invoice_august.pdf");

    expect(screen.queryByText(/C:\\/)).not.toBeInTheDocument();
  });

  it("agent-connected: shows the waiting-for-agent state instead of a fabricated local result", async () => {
    mockSearchFiles.mockResolvedValue({
      status: "ready",
      message: null,
      questions: [],
      interpretation: ['Filename contains "invoice"'],
      queued: true,
      command_id: 42,
      total_files_scanned: 0,
      files_with_errors: 0,
      total_matches: 0,
      returned: 0,
      truncated: false,
      results: [],
    });
    mockGetAgentCommands.mockResolvedValue([]); // never completes -- still polling

    await openSearch();
    typeAndSearch("find invoices");

    expect(await screen.findByText(/waiting for your agent/i)).toBeInTheDocument();
    expect(mockSearchFiles).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));
  });
});

async function openHealth() {
  fireEvent.click(await screen.findByRole("button", { name: /organization health/i }));
}

describe("Dashboard's FileFlow Health panel", () => {
  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 0,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockGetOrganizationHealth.mockReset();
    mockGetUnclassifiedSuggestions.mockReset();
    mockAnalyzeDuplicates.mockReset();
  });

  const HEALTHY_DATA = {
    generated_at: "2026-09-17T12:00:00Z",
    agent_connected: false,
    files: {
      status: "available",
      message: null,
      scanned: 100,
      classified: 96,
      unclassified: 4,
      errors: 0,
      classification_coverage_percent: 96.0,
    },
    duplicates: { status: "available", message: null, groups: 3, duplicate_files: 6, potential_redundant_bytes: 2048 },
    rules: {
      status: "available",
      message: null,
      active: 5,
      disabled: 0,
      conflicts_total: 1,
      conflicts_high: 1,
      conflicts_warning: 0,
      redundant_rules: 0,
    },
    activity: {
      status: "available",
      message: null,
      last_24_hours: { organized: 2, skipped: 0 },
      last_7_days: { organized: 10, skipped: 1 },
      last_30_days: { organized: 20, skipped: 3 },
    },
  };

  it("renders the health panel with real numbers from the API", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);

    renderDashboard();
    await openHealth();

    expect(await screen.findByText("96% classified")).toBeInTheDocument();
    expect(screen.getAllByText(/4 unclassified files/i).length).toBeGreaterThan(0);
  });

  it("shows a loading state before the first response arrives", async () => {
    let resolveIt;
    mockGetOrganizationHealth.mockReturnValue(
      new Promise((resolve) => {
        resolveIt = resolve;
      }),
    );

    renderDashboard();
    await openHealth();

    expect(await screen.findByText(/loading workspace health/i)).toBeInTheDocument();
    resolveIt(HEALTHY_DATA);
    await waitFor(() => expect(screen.queryByText(/loading workspace health/i)).not.toBeInTheDocument());
  });

  it("shows a request-level error instead of crashing the dashboard", async () => {
    mockGetOrganizationHealth.mockRejectedValue(new Error("network error"));

    renderDashboard();
    // The rest of the Dashboard must still work.
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    await openHealth();

    expect(await screen.findByText(/couldn't load workspace health/i)).toBeInTheDocument();
  });

  it("shows unavailable sections without a fabricated zero for an agent-connected account", async () => {
    mockGetOrganizationHealth.mockResolvedValue({
      ...HEALTHY_DATA,
      agent_connected: true,
      files: { status: "unavailable", message: "File classification health isn't available yet for a connected agent." },
      duplicates: { status: "unavailable", message: "Duplicate scanning isn't available yet for a connected agent." },
    });

    renderDashboard();
    await openHealth();

    expect((await screen.findAllByText(/isn't available yet for a connected agent/i)).length).toBe(2);
    expect(screen.queryByText(/% classified/)).not.toBeInTheDocument();
  });

  it("does not automatically trigger AI suggestions, duplicate analysis, or rule conflict checks on load", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);

    renderDashboard();
    await openHealth();
    await screen.findByText("96% classified");

    expect(mockGetUnclassifiedSuggestions).not.toHaveBeenCalled();
    expect(mockAnalyzeDuplicates).not.toHaveBeenCalled();
  });

  it("clicking Review Unclassified opens the existing Unclassified Suggestions dialog", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);
    mockGetUnclassifiedSuggestions.mockResolvedValue({ total: 4, unclassified: 4, suggestions: [] });

    renderDashboard();
    await openHealth();
    await screen.findByText("96% classified");
    fireEvent.click(screen.getAllByText(/review unclassified/i)[0]);

    expect(await screen.findByText("AI Suggestions")).toBeInTheDocument();
    expect(mockGetUnclassifiedSuggestions).toHaveBeenCalledTimes(1);
  });

  it("clicking Review Duplicates opens the existing Duplicate Groups dialog", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);
    mockAnalyzeDuplicates.mockResolvedValue({ queued: false, duplicate_groups: 3, duplicate_files: 6, groups: [] });

    renderDashboard();
    await openHealth();
    await screen.findByText("96% classified");
    fireEvent.click(screen.getAllByText(/review duplicates/i)[0]);

    expect(mockAnalyzeDuplicates).toHaveBeenCalledTimes(1);
  });

  it("clicking Refresh re-fetches health data", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);

    renderDashboard();
    await openHealth();
    await screen.findByText("96% classified");
    fireEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

    // 1 (Dashboard's own mount) + 1 (this Refresh click). Header -- which
    // independently fetches health for its own agent-connected pill -- is
    // rendered at the layout level now, not inside Dashboard's own tree,
    // so it contributes no calls here.
    await waitFor(() => expect(mockGetOrganizationHealth).toHaveBeenCalledTimes(2));
  });

  it("rapid repeated Refresh clicks do not fire duplicate requests", async () => {
    let resolveSecond;
    mockGetOrganizationHealth
      .mockResolvedValueOnce(HEALTHY_DATA) // Dashboard's own mount-effect call
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveSecond = resolve;
        }),
      );

    renderDashboard();
    await openHealth();
    await screen.findByText("96% classified");
    const refreshButton = screen.getByRole("button", { name: /^refresh$/i });

    fireEvent.click(refreshButton);
    fireEvent.click(refreshButton);
    fireEvent.click(refreshButton);
    resolveSecond(HEALTHY_DATA);

    await waitFor(() => expect(screen.queryByText(/refreshing…/i)).not.toBeInTheDocument());
    expect(mockGetOrganizationHealth).toHaveBeenCalledTimes(2);
  });

  it("existing Dashboard functionality (stats, activity table) remains intact alongside the health panel", async () => {
    mockGetOrganizationHealth.mockResolvedValue(HEALTHY_DATA);

    renderDashboard();

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("filed this week")).toBeInTheDocument();
  });
});

describe("Dashboard v5 layout", () => {
  beforeEach(() => {
    mockGetStats.mockResolvedValue({
      total_files_organized: 1,
      duplicates_detected: 0,
      storage_saved_bytes: 0,
      today_count: 12,
      last_7_days: [],
    });
    mockGetCategories.mockResolvedValue([]);
    mockGetWeeklyReports.mockResolvedValue([]);
    mockGetAgentCommands.mockResolvedValue([]);
    mockGetOrganizationHealth.mockReset();
    mockGetOrganizationHealth.mockResolvedValue(DEFAULT_HEALTH);
  });

  it("shows latest slips as a receipt with no Undo / Move to / Why controls", async () => {
    renderDashboard();
    await screen.findByText("report.pdf");

    expect(screen.queryByRole("button", { name: /^undo$/i })).not.toBeInTheDocument();
    expect(screen.queryByTitle("Move this file to a different category")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /why/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /report\.pdf/i })).toHaveAttribute("title", "Open in Activity");
  });

  it("shows the same four machine-room metrics", async () => {
    renderDashboard();
    await screen.findByText("report.pdf");
    for (const label of ["filed this week", "in category folders", "unclassified", "rule conflicts"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("img", { name: "12 files filed today" })).toBeInTheDocument();
  });

  it("no longer renders the old health / agent / active-rules panels inline", async () => {
    renderDashboard();
    await screen.findByText("report.pdf");
    expect(screen.queryByText("FileFlow Health")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Active rules" })).not.toBeInTheDocument();
    expect(screen.queryByText(/get ai suggestions/i)).not.toBeInTheDocument();
  });

  it("adds a Needs you item when an agent command is pending", async () => {
    mockGetAgentCommands.mockImplementation(({ type }) =>
      Promise.resolve(
        type === "undo"
          ? [{ id: 1, type: "undo", status: "pending", success: null, created_at: new Date().toISOString() }]
          : [],
      ),
    );
    renderDashboard();
    expect(await screen.findByRole("button", { name: /agent commands/i })).toBeInTheDocument();
    mockGetAgentCommands.mockReset();
  });

  it("says nothing is waiting when health reports no problems", async () => {
    renderDashboard();
    expect(await screen.findByText(/nothing is waiting on you/i)).toBeInTheDocument();
  });
});
