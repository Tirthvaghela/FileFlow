import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard.jsx";

const mockGetStats = vi.fn();
const mockGetCategories = vi.fn();
const mockGetWeeklyReports = vi.fn();
const mockOrganizeExistingFiles = vi.fn();
const mockReclassifyLog = vi.fn();
const mockUndoLastOperation = vi.fn();
const mockGetAgentCommands = vi.fn();

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

vi.mock("../services/api.js", () => ({
  getStats: (...args) => mockGetStats(...args),
  getCategories: (...args) => mockGetCategories(...args),
  getWeeklyReports: (...args) => mockGetWeeklyReports(...args),
  organizeExistingFiles: (...args) => mockOrganizeExistingFiles(...args),
  reclassifyLog: (...args) => mockReclassifyLog(...args),
  undoLastOperation: (...args) => mockUndoLastOperation(...args),
  getAgentCommands: (...args) => mockGetAgentCommands(...args),
  getLogs: vi.fn().mockResolvedValue(logs),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
}));

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({
    rules: {
      realtime_monitoring_enabled: true,
      keyword_rules: [],
      extension_rules: {},
      large_file_enabled: false,
      categories: { Documents: [".pdf"], Archive: [] },
    },
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
  it("shows an error when a reclassify fails, instead of failing silently", async () => {
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
    mockReclassifyLog.mockRejectedValueOnce({ response: { status: 500 } });
    renderDashboard();

    await screen.findByText("report.pdf");
    fireEvent.change(screen.getByTitle("Move this file to a different category"), {
      target: { value: "Archive" },
    });

    await waitFor(() =>
      expect(screen.getByText(/couldn't reclassify/i)).toBeInTheDocument(),
    );
  });

  it("shows an error when 'Undo last operation' fails, instead of failing silently", async () => {
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
    mockUndoLastOperation.mockRejectedValueOnce({ response: { status: 500 } });
    renderDashboard();

    const undoButton = await screen.findByRole("button", { name: /^undo$/i });
    fireEvent.click(undoButton);

    await waitFor(() =>
      expect(screen.getByText(/couldn't undo the last operation/i)).toBeInTheDocument(),
    );
  });

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
    mockOrganizeExistingFiles.mockRejectedValueOnce({ response: { status: 500 } });
    renderDashboard();

    fireEvent.click(
      await screen.findByRole("button", { name: /organize existing files now/i }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /^organize now$/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/couldn't organize existing files/i),
      ).toBeInTheDocument(),
    );
  });
});
