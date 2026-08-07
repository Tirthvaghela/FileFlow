import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext.jsx";

let capturedUnauthorizedHandler = null;

vi.mock("../services/api.js", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  verifyTwoFactor: vi.fn(),
  setUnauthorizedHandler: vi.fn((handler) => {
    capturedUnauthorizedHandler = handler;
  }),
}));

import { getMe, login, logout, register } from "../services/api.js";

function Consumer() {
  const { user, loading, login: doLogin, logout: doLogout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.email : "none"}</span>
      <button onClick={() => doLogin("fresh@example.com", "pw")}>login</button>
      <button onClick={() => doLogout()}>logout</button>
    </div>
  );
}

// AuthProvider mounts and immediately fires getMe() to check for an
// existing session. These tests guard two real bugs found while auditing
// that flow: a slow/late getMe() overwriting a login the user made in the
// meantime, and a session that expires mid-use leaving the UI silently
// stuck instead of signing the user out.
describe("AuthProvider", () => {
  beforeEach(() => {
    getMe.mockReset();
    login.mockReset();
    logout.mockReset();
    register.mockReset();
    capturedUnauthorizedHandler = null;
  });

  it("does not let a slow, stale getMe() response clobber a fresher login", async () => {
    let resolveGetMe;
    getMe.mockReturnValue(
      new Promise((resolve) => {
        resolveGetMe = resolve;
      }),
    );
    login.mockResolvedValue({ requires_2fa: false, user: { email: "fresh@example.com" } });

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));

    fireEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("fresh@example.com"));

    // The mount-triggered getMe() finally resolves, after the login already
    // landed -- as if it had been checking a stale/anonymous session.
    resolveGetMe(null);
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByTestId("user")).toHaveTextContent("fresh@example.com");
  });

  it("signs the user out when the API layer reports a 401", async () => {
    getMe.mockResolvedValue({ email: "existing@example.com" });

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("existing@example.com"));

    expect(capturedUnauthorizedHandler).toBeInstanceOf(Function);
    capturedUnauthorizedHandler();

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));
  });
});
