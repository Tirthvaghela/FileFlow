import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import CategoryDetail from "./CategoryDetail.jsx";

const mockGetCategoryFiles = vi.fn();
const mockDeleteCategoryFile = vi.fn();

vi.mock("../services/api.js", () => ({
  getCategoryFiles: (...args) => mockGetCategoryFiles(...args),
  deleteCategoryFile: (...args) => mockDeleteCategoryFile(...args),
  // Pulled in transitively by the shared Header component -- not part of
  // what this file is testing, just what's needed to mount the real page.
  getLogs: vi.fn().mockResolvedValue([]),
  agentInstallerUrl: vi.fn(() => "/api/agent-installer"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
  getOrganizationHealth: vi.fn().mockResolvedValue({ agent_connected: false }),
}));

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({ rules: { realtime_monitoring_enabled: true } }),
}));

function file(overrides = {}) {
  return {
    name: "report.pdf",
    path: "C:/watch/Documents/report.pdf",
    size_bytes: 1024,
    modified_at: "2026-01-01T08:00:00Z",
    ...overrides,
  };
}

function renderCategoryDetail() {
  return render(
    <MemoryRouter initialEntries={["/app/categories/Documents"]}>
      <Routes>
        <Route path="/app/categories/:category" element={<CategoryDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CategoryDetail delete failure handling", () => {
  it("surfaces the backend's specific reason for a single-file delete failure", async () => {
    mockGetCategoryFiles.mockResolvedValueOnce([file()]);
    // Real backend contract (routes.py delete_category_file_route /
    // automation/organizer.py delete_category_file): a rejected delete is
    // still an HTTP 200 with success:false and a specific, useful message
    // -- "That file no longer exists.", a path-containment refusal, an
    // agent-connected refusal, or a real OS error. The frontend must not
    // discard this in favor of a generic string when there's exactly one
    // file involved.
    mockDeleteCategoryFile.mockResolvedValueOnce({
      success: false,
      message: "That file no longer exists.",
    });
    renderCategoryDetail();

    await screen.findByText("report.pdf");
    fireEvent.click(screen.getByTitle("Move to Recycle Bin"));
    fireEvent.click(screen.getByRole("button", { name: /move to recycle bin/i }));

    await waitFor(() =>
      expect(screen.getByText("That file no longer exists.")).toBeInTheDocument(),
    );
    // The file must still be listed -- a failed delete must never remove
    // the row.
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("still shows a specific message for a network/transport failure (no message payload)", async () => {
    mockGetCategoryFiles.mockResolvedValueOnce([file()]);
    mockDeleteCategoryFile.mockRejectedValueOnce(new Error("network error"));
    renderCategoryDetail();

    await screen.findByText("report.pdf");
    fireEvent.click(screen.getByTitle("Move to Recycle Bin"));
    fireEvent.click(screen.getByRole("button", { name: /move to recycle bin/i }));

    await waitFor(() =>
      expect(screen.getByText(/couldn't delete/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("removes the row on a successful delete (non-regression)", async () => {
    mockGetCategoryFiles.mockResolvedValueOnce([file()]);
    mockDeleteCategoryFile.mockResolvedValueOnce({ success: true, message: "Deleted." });
    renderCategoryDetail();

    await screen.findByText("report.pdf");
    fireEvent.click(screen.getByTitle("Move to Recycle Bin"));
    fireEvent.click(screen.getByRole("button", { name: /move to recycle bin/i }));

    await waitFor(() => expect(screen.queryByText("report.pdf")).not.toBeInTheDocument());
  });
});
