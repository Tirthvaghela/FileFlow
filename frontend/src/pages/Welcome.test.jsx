import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Welcome from "./Welcome.jsx";

vi.mock("../services/api.js", () => ({
  getOnboardingTemplates: vi.fn(),
  applyOnboardingTemplate: vi.fn(),
  completeOnboarding: vi.fn(),
  getRules: vi.fn(),
  updateRules: vi.fn(),
  updateWatchFolder: vi.fn(),
}));

const mockRefresh = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../context/AuthContext.jsx", () => ({
  useAuth: () => ({
    user: { watch_folder: "C:\\Users\\test\\Downloads", onboarding_completed: false },
    refresh: mockRefresh,
  }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

import { completeOnboarding, getOnboardingTemplates } from "../services/api.js";

// The wizard's most important escape hatch: a user who doesn't want to
// answer three setup questions must still be able to reach the dashboard
// in one click, with onboarding still marked complete on the server.
describe("Welcome", () => {
  beforeEach(() => {
    mockRefresh.mockReset();
    mockNavigate.mockReset();
    getOnboardingTemplates.mockReset().mockResolvedValue([]);
    completeOnboarding.mockReset().mockResolvedValue({ onboarding_completed: true });
  });

  it("skipping setup marks onboarding complete and lands on the dashboard", async () => {
    render(
      <MemoryRouter>
        <Welcome />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Skip setup"));

    await waitFor(() => expect(completeOnboarding).toHaveBeenCalled());
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/app", { replace: true }),
    );
  });
});
