import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actionText, relativeTime } from "./activity.js";

describe("actionText", () => {
  it("maps every real backend action to its display text", () => {
    expect(actionText({ action: "moved", category: "Documents" })).toBe("Moved to Documents");
    expect(actionText({ action: "renamed_and_moved", category: "Images" })).toBe(
      "Renamed duplicate → Images",
    );
    expect(actionText({ action: "replaced", category: "Videos" })).toBe(
      "Replaced existing file in Videos",
    );
    expect(actionText({ action: "duplicate_skipped", category: "Documents" })).toBe(
      "Duplicate skipped",
    );
    expect(actionText({ action: "archived", category: "Archive" })).toBe("Archived from Archive");
  });

  it("falls back to the 'moved' phrasing for an unrecognized action", () => {
    expect(actionText({ action: "something_new", category: "Others" })).toBe("Moved to Others");
  });
});

describe("relativeTime", () => {
  const NOW = new Date("2026-08-03T12:00:00Z");

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function isoMinutesAgo(mins) {
    return new Date(NOW.getTime() - mins * 60_000).toISOString();
  }

  it("returns 'just now' for anything under a minute old", () => {
    expect(relativeTime(isoMinutesAgo(0.5))).toBe("just now");
  });

  it("returns minutes for entries under an hour old", () => {
    expect(relativeTime(isoMinutesAgo(5))).toBe("5m ago");
  });

  it("returns hours for entries under a day old", () => {
    expect(relativeTime(isoMinutesAgo(3 * 60))).toBe("3h ago");
  });

  it("falls back to a formatted date once an entry is a day or older", () => {
    const result = relativeTime(isoMinutesAgo(25 * 60));
    expect(result).not.toMatch(/ago|just now/);
  });
});
