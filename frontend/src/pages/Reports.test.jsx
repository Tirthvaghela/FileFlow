import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Reports from "./Reports.jsx";

const { weekly } = vi.hoisted(() => ({
  weekly: [
    {
      week_start: "2026-08-17",
      week_end: "2026-08-23",
      files_organized: 12,
      duplicates_removed: 2,
      storage_optimized_bytes: 4096,
      files_archived: 1,
    },
  ],
}));

vi.mock("../services/api.js", () => ({
  getWeeklyReports: vi.fn().mockResolvedValue(weekly),
  csvReportUrl: vi.fn((since, until) => `/api/reports/csv?since=${since}&until=${until}`),
  excelReportUrl: vi.fn(() => "/api/reports/excel"),
  pdfReportUrl: vi.fn(() => "/api/reports/pdf"),
  // Pulled in transitively by the shared Header component every page
  // (including Reports) renders -- not part of what this file is testing,
  // just what's needed to mount the real page without crashing.
  getLogs: vi.fn().mockResolvedValue([]),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
}));

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({ rules: { realtime_monitoring_enabled: true } }),
}));

function renderReports() {
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>,
  );
}

describe("Reports page exports", () => {
  it("labels the PDF export as full-history, not scoped to the displayed week", async () => {
    renderReports();

    // The card header and the CSV button both display/use the current
    // week's range (current.week_start/week_end) -- the PDF export must
    // not be presented the same way unless it actually reflects that same
    // period. build_pdf()/`/api/reports/pdf` take no since/until at all
    // (confirmed by direct backend trace: report_service.py's build_pdf
    // always summarizes the account's entire history via get_stats()),
    // so the button text must say so rather than implying it matches the
    // "Weekly report" period shown right above it.
    const pdfLink = await screen.findByRole("link", { name: /export pdf/i });
    expect(pdfLink.textContent).toMatch(/full history/i);
  });

  it("still scopes the CSV export to the currently displayed week", async () => {
    renderReports();

    const csvLink = await screen.findByRole("link", { name: /export csv/i });
    expect(csvLink.getAttribute("href")).toContain("since=2026-08-17");
    expect(csvLink.getAttribute("href")).toContain("until=2026-08-23");
  });

  it("points the PDF export at the unscoped endpoint", async () => {
    renderReports();

    const pdfLink = await screen.findByRole("link", { name: /export pdf/i });
    await waitFor(() => expect(pdfLink.getAttribute("href")).toBe("/api/reports/pdf"));
  });
});
