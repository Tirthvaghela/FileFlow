import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RulesProvider, useRules } from "./RulesContext.jsx";

vi.mock("../services/api.js", () => ({
  getRules: vi.fn(),
  updateRules: vi.fn(),
}));

import { getRules, updateRules } from "../services/api.js";

function Consumer() {
  const { rules, saveRules } = useRules();
  return (
    <div>
      <span data-testid="value">{rules ? rules.archive_after_days : "loading"}</span>
      <button onClick={() => saveRules({ ...rules, archive_after_days: 99 }).catch(() => {})}>
        save
      </button>
    </div>
  );
}

// This provider exists specifically to fix a real bug: Sidebar/Dashboard/
// Rules/Settings each held independent stale copies of rules.json before it
// existed. These tests guard the optimistic-update + rollback mechanism
// that fix depends on.
describe("RulesProvider", () => {
  beforeEach(() => {
    getRules.mockReset();
    updateRules.mockReset();
  });

  it("loads rules once on mount and exposes them to consumers", async () => {
    getRules.mockResolvedValue({ archive_after_days: 30 });

    render(
      <RulesProvider>
        <Consumer />
      </RulesProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("30"));
  });

  it("applies a save optimistically before the request resolves", async () => {
    getRules.mockResolvedValue({ archive_after_days: 30 });
    let resolveUpdate;
    updateRules.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      }),
    );

    render(
      <RulesProvider>
        <Consumer />
      </RulesProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("30"));

    fireEvent.click(screen.getByText("save"));

    // The optimistic setRules(next) happens synchronously, before
    // updateRules' promise ever resolves.
    expect(screen.getByTestId("value")).toHaveTextContent("99");

    resolveUpdate({ archive_after_days: 99 });
    await waitFor(() => expect(updateRules).toHaveBeenCalledTimes(1));
  });

  it("rolls back to the previous value when the save request fails", async () => {
    getRules.mockResolvedValue({ archive_after_days: 30 });
    updateRules.mockRejectedValue(new Error("network error"));

    render(
      <RulesProvider>
        <Consumer />
      </RulesProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("30"));

    fireEvent.click(screen.getByText("save"));
    expect(screen.getByTestId("value")).toHaveTextContent("99"); // optimistic

    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("30")); // rolled back
  });
});
