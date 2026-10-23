import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings.jsx";

const mockGenerateAgentToken = vi.fn();
const mockAddWatchFolder = vi.fn();
const mockRemoveWatchFolder = vi.fn();
const mockBrowseFolder = vi.fn();
const mockDeleteAccount = vi.fn();
const mockDisableTwoFactor = vi.fn();
const mockEnableTwoFactor = vi.fn();
const mockGetTwoFactorStatus = vi.fn();

vi.mock("../services/api.js", () => ({
  addWatchFolder: (...args) => mockAddWatchFolder(...args),
  browseFolder: (...args) => mockBrowseFolder(...args),
  deleteAccount: (...args) => mockDeleteAccount(...args),
  disableTwoFactor: (...args) => mockDisableTwoFactor(...args),
  enableTwoFactor: (...args) => mockEnableTwoFactor(...args),
  generateAgentToken: (...args) => mockGenerateAgentToken(...args),
  getTwoFactorStatus: (...args) => mockGetTwoFactorStatus(...args),
  removeWatchFolder: (...args) => mockRemoveWatchFolder(...args),
  setupTwoFactor: vi.fn(),
  updateWatchFolder: vi.fn(),
  // Pulled in transitively by the shared Header component every page
  // (including Settings) renders -- not part of what this file is testing,
  // just what's needed to mount the real page without crashing.
  getLogs: vi.fn().mockResolvedValue([]),
  agentInstallerUrl: vi.fn(() => "/api/agent/download"),
  simulateDownloadUrl: vi.fn(() => "/api/simulate-download"),
  wsUrl: vi.fn(() => "ws://localhost/ws"),
  getOrganizationHealth: vi.fn().mockResolvedValue({ agent_connected: false }),
}));
// A persistent default so every describe block that doesn't care about 2FA
// status specifically (i.e. everything except the 2FA-focused block below)
// doesn't need to configure it -- mockResolvedValueOnce in those tests
// takes priority over this for exactly the one call it's queued for.
mockGetTwoFactorStatus.mockResolvedValue({ enabled: false });

const mockSaveRules = vi.fn();
const mockRefresh = vi.fn();

vi.mock("../context/RulesContext.jsx", () => ({
  useRules: () => ({
    rules: {
      realtime_monitoring_enabled: true,
      desktop_notifications_enabled: true,
      scheduled_organize_enabled: false,
      scheduled_organize_time: "02:00",
      duplicate_handling: "rename",
      archive_after_days: 30,
      large_file_threshold_mb: 500,
      recycle_bin_retention_days: 30,
      storage_alert_threshold_gb: 0,
      archive_folder: "Archive",
      default_category: "Others",
    },
    saveRules: mockSaveRules,
  }),
}));

const mockLogout = vi.fn();
let mockUser;
vi.mock("../context/AuthContext.jsx", () => ({
  useAuth: () => ({
    user: mockUser,
    refresh: mockRefresh,
    logout: mockLogout,
  }),
}));

// Renders the real Settings page and waits for its one unconditional async
// effect (getTwoFactorStatus) to settle -- without this, React logs "not
// wrapped in act(...)" for a state update that lands after the test's own
// assertions already ran, since nothing else in these tests depends on it.
async function renderSettings() {
  render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: /set up 2fa/i });
}

const WARNING_TEXT = /remote agent watches only one folder/i;

describe("Settings' remote-agent one-folder limitation warning", () => {
  beforeEach(() => {
    mockSaveRules.mockReset();
    mockRefresh.mockReset();
  });

  it("is absent when the agent is disconnected and there are no additional folders", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: [],
      agent_connected: false,
    };
    await renderSettings();

    expect(screen.queryByText(WARNING_TEXT)).not.toBeInTheDocument();
  });

  it("is absent when the agent is disconnected even with additional folders configured", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: false,
    };
    await renderSettings();

    expect(screen.queryByText(WARNING_TEXT)).not.toBeInTheDocument();
  });

  it("is absent when the agent is connected but there are no additional folders", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: [],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.queryByText(WARNING_TEXT)).not.toBeInTheDocument();
  });

  it("appears when the agent is connected and an additional folder is configured", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.getByText(WARNING_TEXT)).toBeInTheDocument();
  });

  it("appears with exactly one additional folder configured", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\just-one"],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.getByText(WARNING_TEXT)).toBeInTheDocument();
  });

  it("appears with multiple additional folders configured", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra", "E:\\more"],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.getByText(WARNING_TEXT)).toBeInTheDocument();
  });

  it("never renders an agent token, Authorization header, or another account's data", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: true,
    };
    await renderSettings();

    const rendered = document.body.textContent;
    expect(rendered).not.toMatch(/bearer/i);
    expect(rendered).not.toMatch(/authorization/i);
    // The warning is scoped to the acting user's own `user` object only --
    // no other account id/email ever enters this component's render path.
    expect(rendered).not.toMatch(/other@example\.com/i);
  });

  it("does not name a specific folder as the one the agent covers -- that information isn't available", async () => {
    // D:\extra legitimately appears elsewhere on the page (the additional-
    // folders management list above) -- this scopes the check to the
    // warning banner's own text only, since the backend has no way to know
    // which folder the agent is actually configured for.
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: true,
    };
    await renderSettings();

    const warningText = screen.getByText(WARNING_TEXT).closest("div").textContent;
    expect(warningText).not.toContain("D:\\extra");
  });

  it("existing add/remove watch-folder controls still render and are untouched", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.getByText("D:\\extra")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add folder/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/stop watching d:\\extra/i)).toBeInTheDocument();
  });

  it("existing remote-agent token-generation UI still renders untouched", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: true,
    };
    await renderSettings();

    expect(screen.getByRole("heading", { name: "Remote agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate agent token/i })).toBeInTheDocument();
  });
});

describe("Agent token generation failure handling", () => {
  beforeEach(() => {
    mockSaveRules.mockReset();
    mockRefresh.mockReset();
    mockGenerateAgentToken.mockReset();
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: [],
      agent_connected: false,
    };
  });

  it("shows an error when token generation fails, instead of failing silently", async () => {
    mockGenerateAgentToken.mockRejectedValueOnce({ response: { status: 500 } });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /generate agent token/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generate agent token/i })).toBeEnabled(),
    );

    // The bug: handleGenerateAgentToken had no catch block at all, so a
    // rejected request left the user with zero indication anything went
    // wrong -- the button just silently returned to its normal label.
    expect(screen.getByText(/couldn't generate|failed/i)).toBeInTheDocument();
  });

  it("does not display a token that was never actually issued", async () => {
    mockGenerateAgentToken.mockRejectedValueOnce({ response: { status: 500 } });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /generate agent token/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generate agent token/i })).toBeEnabled(),
    );

    expect(screen.queryByText(/shown once/i)).not.toBeInTheDocument();
  });

  it("still displays the token on a successful generation (non-regression)", async () => {
    mockGenerateAgentToken.mockResolvedValueOnce({
      token: "fake-agent-token-for-testing-only",
      scope: "full",
    });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /generate agent token/i }));

    expect(await screen.findByText("fake-agent-token-for-testing-only")).toBeInTheDocument();
    expect(screen.queryByText(/couldn't generate|failed/i)).not.toBeInTheDocument();
  });
});

describe("Additional watch-folder add/remove failure handling", () => {
  beforeEach(() => {
    mockRefresh.mockReset();
    mockAddWatchFolder.mockReset();
    mockRemoveWatchFolder.mockReset();
    mockBrowseFolder.mockReset();
  });

  it("a failed add leaves the existing folder list untouched and shows an error", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: false,
    };
    mockBrowseFolder.mockResolvedValueOnce({ path: "E:\\new folder" });
    mockAddWatchFolder.mockRejectedValueOnce({
      response: { data: { detail: "That folder overlaps an existing one." } },
    });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /add folder/i }));

    await waitFor(() =>
      expect(screen.getByText("That folder overlaps an existing one.")).toBeInTheDocument(),
    );
    // refreshUser() is only called after a *successful* add -- a failure
    // must not pull in server state that never actually changed, and the
    // pre-existing folder must still be shown.
    expect(mockRefresh).not.toHaveBeenCalled();
    expect(screen.getByText("D:\\extra")).toBeInTheDocument();
    expect(screen.queryByText("E:\\new folder")).not.toBeInTheDocument();
  });

  it("a failed remove leaves the folder in the list and shows an error", async () => {
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: ["D:\\extra"],
      agent_connected: false,
    };
    mockRemoveWatchFolder.mockRejectedValueOnce(new Error("network error"));
    await renderSettings();

    fireEvent.click(screen.getByLabelText(/stop watching d:\\extra/i));

    await waitFor(() =>
      expect(screen.getByText(/couldn't remove that folder/i)).toBeInTheDocument(),
    );
    expect(mockRefresh).not.toHaveBeenCalled();
    expect(screen.getByText("D:\\extra")).toBeInTheDocument();
  });
});

describe("Account deletion failure handling", () => {
  beforeEach(() => {
    mockDeleteAccount.mockReset();
    mockLogout.mockReset();
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: [],
      agent_connected: false,
    };
  });

  it("a failed deletion keeps the user logged in and shows an error, without logging out", async () => {
    mockDeleteAccount.mockRejectedValueOnce({
      response: { data: { detail: "Incorrect password." } },
    });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^delete account$/i }));

    await waitFor(() => expect(screen.getByText("Incorrect password.")).toBeInTheDocument());
    // The two must-not-happen-on-failure behaviors from the task's own
    // checklist: never actually logs out, never navigates away.
    expect(mockLogout).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /delete account/i })).toBeEnabled();
  });
});

describe("2FA enable/disable failure handling", () => {
  beforeEach(() => {
    mockEnableTwoFactor.mockReset();
    mockDisableTwoFactor.mockReset();
    mockGetTwoFactorStatus.mockReset();
    mockUser = {
      id: 1,
      watch_folder: "C:\\watch",
      additional_watch_folders: [],
      agent_connected: false,
    };
  });

  it("an enable failure does not claim 2FA is enabled or show backup codes", async () => {
    // setupTwoFactor's mock already resolves undefined by default, which
    // is enough to get from "Set up 2FA" into the QR/code-entry view.
    const { setupTwoFactor } = await import("../services/api.js");
    setupTwoFactor.mockResolvedValueOnce({
      secret: "FAKE2FASECRETNOTREAL",
      qr_code_data_uri: "data:image/png;base64,fake",
    });
    mockGetTwoFactorStatus.mockResolvedValueOnce({ enabled: false });
    mockEnableTwoFactor.mockRejectedValueOnce({
      response: { data: { detail: "That code is incorrect." } },
    });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /set up 2fa/i }));
    await screen.findByLabelText(/6-digit code/i);
    fireEvent.change(screen.getByLabelText(/6-digit code/i), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /^enable$/i }));

    await waitFor(() => expect(screen.getByText("That code is incorrect.")).toBeInTheDocument());
    expect(screen.queryByText(/save these backup codes/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^enabled$/i)).not.toBeInTheDocument();
    // The QR/manual-entry step must still be showing, so the user can
    // simply retype the code rather than restarting setup from scratch.
    expect(screen.getByAltText(/2fa setup qr code/i)).toBeInTheDocument();
  });

  it("a disable failure preserves the enabled state and does not close the dialog", async () => {
    mockGetTwoFactorStatus.mockResolvedValueOnce({ enabled: true });
    mockDisableTwoFactor.mockRejectedValueOnce({
      response: { data: { detail: "Incorrect password." } },
    });
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    await screen.findByText(/^enabled$/i);

    fireEvent.click(screen.getByRole("button", { name: /^disable$/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /^disable$/i }));

    await waitFor(() => expect(screen.getByText("Incorrect password.")).toBeInTheDocument());
    expect(screen.getByText(/^enabled$/i)).toBeInTheDocument();
  });
});

describe("Settings v5 layout", () => {
  beforeEach(() => {
    mockSaveRules.mockReset();
    mockSaveRules.mockResolvedValue({});
    mockUser = { id: 1, watch_folder: "C:\\watch", additional_watch_folders: [], agent_connected: false };
    mockGetTwoFactorStatus.mockResolvedValue({ enabled: false });
  });

  it("shows a numbered section nav with live states", async () => {
    await renderSettings();
    const nav = screen.getByRole("navigation", { name: /settings sections/i });
    expect(nav).toHaveTextContent("01Watch folders1 folder");
    expect(nav).toHaveTextContent("Auto-sort on");
    expect(nav).toHaveTextContent("Rename · 30 days");
    expect(nav).toHaveTextContent("Not connected");
  });

  it("picks duplicate handling with radio cards", async () => {
    await renderSettings();
    const skip = screen.getByRole("radio", { name: /skip/i });
    expect(screen.getByRole("radio", { name: /rename/i })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(skip);
    await waitFor(() => expect(mockSaveRules).toHaveBeenCalledTimes(1));
    expect(mockSaveRules.mock.calls[0][0]({})).toEqual({ duplicate_handling: "skip" });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("renders every toggle as a labelled switch", async () => {
    await renderSettings();
    for (const name of [/real-time monitoring/i, /desktop notifications/i, /scheduled nightly sweep/i]) {
      expect(screen.getByRole("switch", { name })).toBeInTheDocument();
    }
  });
});
