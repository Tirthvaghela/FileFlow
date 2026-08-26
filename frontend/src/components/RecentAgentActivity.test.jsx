import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecentAgentActivity from "./RecentAgentActivity.jsx";

vi.mock("../services/api.js", () => ({
  getAgentCommands: vi.fn(),
}));

import { getAgentCommands } from "../services/api.js";

function mockResponses({ undo = [], reclassify = [] } = {}) {
  getAgentCommands.mockImplementation(({ type }) => {
    if (type === "undo") return Promise.resolve(undo);
    if (type === "reclassify") return Promise.resolve(reclassify);
    return Promise.resolve([]);
  });
}

describe("RecentAgentActivity", () => {
  beforeEach(() => {
    getAgentCommands.mockReset();
  });

  it("requests both undo and reclassify commands separately, never organize_existing", async () => {
    mockResponses();

    render(<RecentAgentActivity />);

    await waitFor(() => expect(getAgentCommands).toHaveBeenCalledTimes(2));
    expect(getAgentCommands).toHaveBeenCalledWith({ type: "undo", limit: 10 });
    expect(getAgentCommands).toHaveBeenCalledWith({ type: "reclassify", limit: 10 });
  });

  it("shows a loading state before both requests resolve", () => {
    getAgentCommands.mockReturnValue(new Promise(() => {}));

    render(<RecentAgentActivity />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an empty state when there is no undo/reclassify activity", async () => {
    mockResponses();

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText(/no recent undo\/reclassify activity/i)).toBeInTheDocument());
  });

  it("shows an error state when either request fails", async () => {
    getAgentCommands.mockRejectedValue(new Error("network error"));

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText(/couldn't load recent activity/i)).toBeInTheDocument());
  });

  it("renders reclassify activity with its action label", async () => {
    mockResponses({
      reclassify: [
        {
          id: 1,
          type: "reclassify",
          status: "done",
          success: true,
          error: null,
          result: { destination_path: "C:\\watch\\Archive\\report.pdf" },
          created_at: "2026-01-01T08:15:00Z",
          completed_at: "2026-01-01T08:15:02Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText("Reclassify")).toBeInTheDocument());
  });

  it("renders undo activity with its action label", async () => {
    mockResponses({
      undo: [
        {
          id: 2,
          type: "undo",
          status: "done",
          success: true,
          error: null,
          result: {},
          created_at: "2026-01-01T08:10:00Z",
          completed_at: "2026-01-01T08:10:01Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText("Undo")).toBeInTheDocument());
  });

  it("renders a pending command as Waiting for agent, with no invented result", async () => {
    mockResponses({
      undo: [
        {
          id: 3,
          type: "undo",
          status: "pending",
          success: null,
          error: null,
          result: {},
          created_at: "2026-01-01T08:20:00Z",
          completed_at: null,
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText(/waiting for agent/i)).toBeInTheDocument());
    const row = screen.getByText(/waiting for agent/i).closest("tr");
    expect(row.textContent).toContain("—");
  });

  it("renders a completed reclassify command's real destination category, not an invented count", async () => {
    mockResponses({
      reclassify: [
        {
          id: 4,
          type: "reclassify",
          status: "done",
          success: true,
          error: null,
          result: { destination_path: "C:\\watch\\Finance\\invoice.pdf" },
          created_at: "2026-01-01T08:15:00Z",
          completed_at: "2026-01-01T08:15:02Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText(/moved to finance/i)).toBeInTheDocument());
    // Never a fabricated file count -- reclassify's actual persisted result
    // has no such field.
    expect(screen.queryByText(/\d+ files?/i)).not.toBeInTheDocument();
  });

  it("renders a completed undo command's real outcome, not an invented count", async () => {
    mockResponses({
      undo: [
        {
          id: 5,
          type: "undo",
          status: "done",
          success: true,
          error: null,
          result: {},
          created_at: "2026-01-01T08:10:00Z",
          completed_at: "2026-01-01T08:10:01Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText("Restored")).toBeInTheDocument());
    expect(screen.queryByText(/\d+ files?/i)).not.toBeInTheDocument();
  });

  it("shows -- when a completed reclassify command's result is missing the destination path", async () => {
    mockResponses({
      reclassify: [
        {
          id: 6,
          type: "reclassify",
          status: "done",
          success: true,
          error: null,
          result: {},
          created_at: "2026-01-01T08:15:00Z",
          completed_at: "2026-01-01T08:15:02Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText("Reclassify")).toBeInTheDocument());
    const row = screen.getByText("Reclassify").closest("tr");
    expect(row.textContent).toContain("—");
  });

  it("renders a failed command distinctly, showing Failed rather than a fabricated result", async () => {
    mockResponses({
      reclassify: [
        {
          id: 7,
          type: "reclassify",
          status: "done",
          success: false,
          error: "File no longer exists.",
          result: {},
          created_at: "2026-01-01T08:05:00Z",
          completed_at: "2026-01-01T08:05:01Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getAllByText("Failed").length).toBeGreaterThanOrEqual(1));
  });

  it("orders merged undo and reclassify activity newest first", async () => {
    mockResponses({
      undo: [
        {
          id: 8,
          type: "undo",
          status: "done",
          success: true,
          error: null,
          result: {},
          created_at: "2026-01-01T08:00:00Z",
          completed_at: "2026-01-01T08:00:01Z",
        },
      ],
      reclassify: [
        {
          id: 9,
          type: "reclassify",
          status: "done",
          success: true,
          error: null,
          result: { destination_path: "C:\\watch\\Images\\a.jpg" },
          created_at: "2026-01-01T09:00:00Z",
          completed_at: "2026-01-01T09:00:01Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByTestId("recent-agent-activity")).toBeInTheDocument());
    const actionCells = screen.getAllByRole("row").slice(1).map((row) => row.children[1].textContent);
    expect(actionCells).toEqual(["Reclassify", "Undo"]);
  });

  it("never renders a token, Authorization header, or raw payload", async () => {
    mockResponses({
      undo: [
        {
          id: 10,
          type: "undo",
          status: "done",
          success: true,
          error: null,
          result: {},
          created_at: "2026-01-01T08:00:00Z",
          completed_at: "2026-01-01T08:00:01Z",
        },
      ],
    });

    render(<RecentAgentActivity />);

    await waitFor(() => expect(screen.getByText("Undo")).toBeInTheDocument());
    const rendered = document.body.textContent;
    expect(rendered).not.toMatch(/bearer/i);
    expect(rendered).not.toMatch(/authorization/i);
    expect(rendered).not.toMatch(/token/i);
  });
});
