import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCommandStatusByLogId } from "./useCommandStatusByLogId.js";

vi.mock("../services/api.js", () => ({
  getAgentCommands: vi.fn(),
}));

import { getAgentCommands } from "../services/api.js";

function Consumer() {
  const { commandStatusByLogId, commandStatusLoadError } = useCommandStatusByLogId();
  return (
    <div>
      <span data-testid="error">{commandStatusLoadError ? "error" : "ok"}</span>
      <span data-testid="dump">{JSON.stringify(commandStatusByLogId)}</span>
    </div>
  );
}

function mockResponses({ undo = [], reclassify = [] } = {}) {
  getAgentCommands.mockImplementation(({ type }) => {
    if (type === "undo") return Promise.resolve(undo);
    if (type === "reclassify") return Promise.resolve(reclassify);
    return Promise.resolve([]);
  });
}

describe("useCommandStatusByLogId", () => {
  beforeEach(() => {
    getAgentCommands.mockReset();
  });

  it("builds a lookup keyed by each command's log_id", async () => {
    mockResponses({
      undo: [{ id: 1, type: "undo", status: "done", success: true, log_id: 10, created_at: "2026-01-01T08:00:00Z" }],
      reclassify: [
        { id: 2, type: "reclassify", status: "pending", success: null, log_id: 11, created_at: "2026-01-01T08:05:00Z" },
      ],
    });

    render(<Consumer />);

    await waitFor(() => {
      const dump = JSON.parse(screen.getByTestId("dump").textContent);
      expect(Object.keys(dump).sort()).toEqual(["10", "11"]);
    });
  });

  it("keeps the newest command when the same log_id has more than one", async () => {
    mockResponses({
      reclassify: [
        // Backend already returns newest-first (higher id = newer).
        { id: 5, type: "reclassify", status: "done", success: true, log_id: 20, created_at: "2026-01-02T08:00:00Z" },
        { id: 3, type: "reclassify", status: "done", success: false, log_id: 20, created_at: "2026-01-01T08:00:00Z" },
      ],
    });

    render(<Consumer />);

    await waitFor(() => {
      const dump = JSON.parse(screen.getByTestId("dump").textContent);
      expect(dump["20"].id).toBe(5);
      expect(dump["20"].success).toBe(true);
    });
  });

  it("ignores commands with no log_id (e.g. organize_existing would never appear here anyway)", async () => {
    mockResponses({
      undo: [{ id: 1, type: "undo", status: "done", success: true, log_id: null, created_at: "2026-01-01T08:00:00Z" }],
    });

    render(<Consumer />);

    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("ok"));
    const dump = JSON.parse(screen.getByTestId("dump").textContent);
    expect(dump).toEqual({});
  });

  it("reports a load error without throwing when the API call fails", async () => {
    getAgentCommands.mockRejectedValue(new Error("network error"));

    render(<Consumer />);

    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("error"));
  });
});
