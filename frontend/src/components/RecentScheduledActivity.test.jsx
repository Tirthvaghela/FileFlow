import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecentScheduledActivity from "./RecentScheduledActivity.jsx";

vi.mock("../services/api.js", () => ({
  getAgentCommands: vi.fn(),
}));

import { getAgentCommands } from "../services/api.js";

describe("RecentScheduledActivity", () => {
  beforeEach(() => {
    getAgentCommands.mockReset();
  });

  it("requests only scheduled organize_existing commands", async () => {
    getAgentCommands.mockResolvedValue([]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(getAgentCommands).toHaveBeenCalledTimes(1));
    expect(getAgentCommands).toHaveBeenCalledWith({
      type: "organize_existing",
      source: "scheduled",
      limit: 10,
    });
  });

  it("shows a loading state before the request resolves", () => {
    getAgentCommands.mockReturnValue(new Promise(() => {}));

    render(<RecentScheduledActivity />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an empty state when there is no scheduled activity yet", async () => {
    getAgentCommands.mockResolvedValue([]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText(/no scheduled organize activity/i)).toBeInTheDocument());
  });

  it("shows an error state when the request fails", async () => {
    getAgentCommands.mockRejectedValue(new Error("network error"));

    render(<RecentScheduledActivity />);

    await waitFor(() =>
      expect(screen.getByText(/couldn't load recent scheduled activity/i)).toBeInTheDocument(),
    );
  });

  it("renders a pending command without displaying misleading zero counts", async () => {
    getAgentCommands.mockResolvedValue([
      {
        id: 1,
        type: "organize_existing",
        status: "pending",
        success: null,
        error: null,
        result: {},
        created_at: "2026-01-01T02:00:00Z",
        completed_at: null,
      },
    ]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText(/waiting for agent/i)).toBeInTheDocument());
    const row = screen.getByText(/waiting for agent/i).closest("tr");
    // Not organized yet -- must show "--", never 0, which would falsely
    // claim a completed run that organized nothing.
    expect(row.textContent).toContain("—");
    expect(row.textContent).not.toMatch(/\b0\b/);
  });

  it("renders a completed command's real organize/duplicate/error counts", async () => {
    getAgentCommands.mockResolvedValue([
      {
        id: 2,
        type: "organize_existing",
        status: "done",
        success: true,
        error: null,
        result: { scanned: 15, organized: 12, duplicates: 1, errors: 2 },
        created_at: "2026-01-01T08:10:00Z",
        completed_at: "2026-01-01T08:10:05Z",
      },
    ]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText("Completed")).toBeInTheDocument());
    const row = screen.getByText("Completed").closest("tr");
    expect(row.textContent).toContain("12");
    expect(row.textContent).toContain("1");
    expect(row.textContent).toContain("2");
  });

  it("renders a completed run that organized zero files as a real zero, not a dash", async () => {
    getAgentCommands.mockResolvedValue([
      {
        id: 3,
        type: "organize_existing",
        status: "done",
        success: true,
        error: null,
        result: { scanned: 0, organized: 0, duplicates: 0, errors: 0 },
        created_at: "2026-01-01T03:00:00Z",
        completed_at: "2026-01-01T03:00:01Z",
      },
    ]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText("Completed")).toBeInTheDocument());
    const row = screen.getByText("Completed").closest("tr");
    // A genuinely-completed run with nothing to organize reports real
    // zeros, not the pending "--" placeholder.
    expect(row.querySelectorAll("td")[2].textContent).toBe("0");
  });

  it("renders a failed command distinctly from completed or pending", async () => {
    getAgentCommands.mockResolvedValue([
      {
        id: 4,
        type: "organize_existing",
        status: "done",
        success: false,
        error: "simulated failure",
        result: {},
        created_at: "2026-01-01T02:00:00Z",
        completed_at: "2026-01-01T02:00:02Z",
      },
    ]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText("Failed")).toBeInTheDocument());
  });

  it("never renders a token, Authorization header, or raw payload", async () => {
    getAgentCommands.mockResolvedValue([
      {
        id: 5,
        type: "organize_existing",
        status: "done",
        success: true,
        error: null,
        result: { scanned: 1, organized: 1, duplicates: 0, errors: 0 },
        created_at: "2026-01-01T02:00:00Z",
        completed_at: "2026-01-01T02:00:02Z",
      },
    ]);

    render(<RecentScheduledActivity />);

    await waitFor(() => expect(screen.getByText("Completed")).toBeInTheDocument());
    const rendered = document.body.textContent;
    expect(rendered).not.toMatch(/bearer/i);
    expect(rendered).not.toMatch(/authorization/i);
    expect(rendered).not.toMatch(/token/i);
  });
});
