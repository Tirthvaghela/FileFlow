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

  it("never loses either update when two independent saves overlap", async () => {
    // Regression test for a real bug: two saveRules() calls fired before
    // either's PUT resolved each built their payload from the same
    // pre-save `rules`, so whichever response landed last silently
    // overwrote the other's change on the server. The fix (an updater
    // function resolved against the latest *optimistic* state, plus a
    // queue that serializes the actual network calls) means both changes
    // must always survive, in either response-arrival order.
    getRules.mockResolvedValue({ archive_after_days: 30, large_file_enabled: false });
    updateRules.mockImplementation((body) => Promise.resolve(body));

    function TwoFieldConsumer() {
      const { rules, saveRules } = useRules();
      if (!rules) return <span data-testid="value">loading</span>;
      return (
        <div>
          <span data-testid="value">
            {rules.archive_after_days}/{String(rules.large_file_enabled)}
          </span>
          <button
            onClick={() => saveRules((current) => ({ ...current, archive_after_days: 99 }))}
          >
            save-days
          </button>
          <button
            onClick={() =>
              saveRules((current) => ({ ...current, large_file_enabled: !current.large_file_enabled }))
            }
          >
            save-large-file
          </button>
        </div>
      );
    }

    render(
      <RulesProvider>
        <TwoFieldConsumer />
      </RulesProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("30/false"));

    fireEvent.click(screen.getByText("save-days"));
    fireEvent.click(screen.getByText("save-large-file"));

    await waitFor(() => expect(updateRules).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("99/true"));

    // The second PUT must have carried the first save's change too --
    // otherwise the server itself would have lost the update even though
    // the client's optimistic UI looked fine.
    const secondCallBody = updateRules.mock.calls[1][0];
    expect(secondCallBody).toMatchObject({ archive_after_days: 99, large_file_enabled: true });
  });
});
