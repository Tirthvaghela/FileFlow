import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import History from "./History.jsx";

const mockUndoLastOperation = vi.fn();
const mockUndoLog = vi.fn();
const mockReclassifyLog = vi.fn();
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
  undoLastOperation: (...args) => mockUndoLastOperation(...args),
  undoLog: (...args) => mockUndoLog(...args),
  reclassifyLog: (...args) => mockReclassifyLog(...args),
  getAgentCommands: (...args) => mockGetAgentCommands(...args),
  getLogs: vi.fn().mockResolvedValue(logs),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
}));

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({ rules: { categories: { Documents: [".pdf"], Archive: [] } } }),
}));

function renderHistory() {
  return render(
    <MemoryRouter>
      <History />
    </MemoryRouter>,
  );
}

describe("History undo/reclassify failure handling", () => {
  it("shows an error when 'Undo last operation' fails, instead of failing silently", async () => {
    mockGetAgentCommands.mockResolvedValue([]);
    mockUndoLastOperation.mockRejectedValueOnce({ response: { status: 500 } });
    renderHistory();

    await screen.findByText("report.pdf");
    fireEvent.click(screen.getByRole("button", { name: /undo last operation/i }));

    await waitFor(() => expect(screen.getByText(/couldn't undo/i)).toBeInTheDocument());
  });

  it("shows an error when a row's Undo fails, instead of failing silently", async () => {
    mockGetAgentCommands.mockResolvedValue([]);
    mockUndoLog.mockRejectedValueOnce({ response: { status: 500 } });
    renderHistory();

    const row = await screen.findByText("report.pdf");
    fireEvent.click(row.closest("div.flex").querySelector("button"));

    await waitFor(() => expect(screen.getByText(/couldn't undo/i)).toBeInTheDocument());
    // The per-row undo button must re-enable after the failure, not stay
    // stuck disabled forever.
    expect(screen.getByRole("button", { name: /^undo$/i })).toBeEnabled();
  });

  it("shows an error when a reclassify fails, instead of failing silently", async () => {
    mockGetAgentCommands.mockResolvedValue([]);
    mockReclassifyLog.mockRejectedValueOnce({ response: { status: 500 } });
    renderHistory();

    await screen.findByText("report.pdf");
    fireEvent.change(screen.getByTitle("Move this file to a different category"), {
      target: { value: "Archive" },
    });

    await waitFor(() => expect(screen.getByText(/couldn't reclassify/i)).toBeInTheDocument());
  });

  it("still shows the backend's own message on a successful undo (non-regression)", async () => {
    mockGetAgentCommands.mockResolvedValue([]);
    mockUndoLog.mockResolvedValueOnce({ success: true, message: "Restored to its original location." });
    renderHistory();

    const row = await screen.findByText("report.pdf");
    fireEvent.click(row.closest("div.flex").querySelector("button"));

    expect(await screen.findByText("Restored to its original location.")).toBeInTheDocument();
  });

  it("does not fire a second 'undo last' request from a rapid double-click", async () => {
    mockGetAgentCommands.mockResolvedValue([]);
    // This mock is shared (module-level) across every test in this describe
    // block and isn't auto-reset between them -- clear its call count so
    // this test's assertion isn't polluted by earlier tests' clicks.
    mockUndoLastOperation.mockClear();
    let resolveUndo;
    mockUndoLastOperation.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUndo = resolve;
      }),
    );
    renderHistory();

    await screen.findByText("report.pdf");
    const undoLastButton = screen.getByRole("button", { name: /undo last operation/i });
    // The backend's atomic claim guarantees two concurrent "undo last" calls
    // each undo a DIFFERENT row (the two most recent) -- so an unguarded
    // double-click doesn't collide, it silently undoes two operations
    // instead of the one the user intended. The button must disable itself
    // the instant the first request is in flight.
    fireEvent.click(undoLastButton);
    await waitFor(() => expect(undoLastButton).toBeDisabled());
    fireEvent.click(undoLastButton);
    fireEvent.click(undoLastButton);

    expect(mockUndoLastOperation).toHaveBeenCalledTimes(1);

    resolveUndo({ success: true, message: "Restored to its original location." });
    await waitFor(() => expect(undoLastButton).toBeEnabled());
  });
});
