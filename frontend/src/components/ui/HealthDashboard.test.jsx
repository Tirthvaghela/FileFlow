import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import HealthDashboard from "./HealthDashboard.jsx";

const HEALTHY_DATA = {
  generated_at: "2026-09-17T12:00:00Z",
  agent_connected: false,
  files: {
    status: "available",
    message: null,
    scanned: 1284,
    classified: 1211,
    unclassified: 73,
    errors: 0,
    classification_coverage_percent: 94.3,
  },
  duplicates: {
    status: "available",
    message: null,
    groups: 18,
    duplicate_files: 41,
    potential_redundant_bytes: 44669337,
  },
  rules: {
    status: "available",
    message: null,
    active: 7,
    disabled: 2,
    conflicts_total: 2,
    conflicts_high: 1,
    conflicts_warning: 1,
    redundant_rules: 1,
  },
  activity: {
    status: "available",
    message: null,
    last_24_hours: { organized: 18, skipped: 2 },
    last_7_days: { organized: 84, skipped: 6 },
    last_30_days: { organized: 200, skipped: 10 },
  },
};

function baseProps(overrides = {}) {
  return {
    data: null,
    loading: false,
    error: "",
    refreshing: false,
    onRefresh: vi.fn(),
    onReviewUnclassified: vi.fn(),
    onReviewDuplicates: vi.fn(),
    ...overrides,
  };
}

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("HealthDashboard", () => {
  it("renders the panel title", () => {
    renderWithRouter(<HealthDashboard {...baseProps()} />);
    expect(screen.getByText("FileFlow Health")).toBeInTheDocument();
  });

  it("shows a loading state before data arrives", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ loading: true })} />);
    expect(screen.getByText(/loading workspace health/i)).toBeInTheDocument();
  });

  it("renders classification coverage with units", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByText("94.3% classified")).toBeInTheDocument();
  });

  it("renders unclassified count", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getAllByText(/73 unclassified files/i).length).toBeGreaterThan(0);
  });

  it("renders duplicate metrics with units", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByText("18 groups")).toBeInTheDocument();
    expect(screen.getByText(/41 duplicate files/)).toBeInTheDocument();
    expect(screen.getByText(/42\.6 MB potentially redundant/)).toBeInTheDocument();
  });

  it("renders rule metrics", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByText("7 active rules")).toBeInTheDocument();
    expect(screen.getAllByText(/2 conflicts/i).length).toBeGreaterThan(0);
  });

  it("renders activity metrics", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    // Exact text: a pluralizing helper once rendered "84 organizeds (7d)"
    // and a looser regex here let it through unnoticed.
    expect(screen.getByText("84 organized (7d)")).toBeInTheDocument();
    expect(screen.getByText(/18 today/)).toBeInTheDocument();
  });

  it("renders a Needs Attention section with every real problem", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getAllByText(/73 unclassified files/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/duplicate group/i).length).toBeGreaterThan(0);
  });

  it("does not render a Needs Attention section when everything is healthy", () => {
    const clean = {
      ...HEALTHY_DATA,
      files: { ...HEALTHY_DATA.files, unclassified: 0, errors: 0 },
      duplicates: { ...HEALTHY_DATA.duplicates, groups: 0 },
      rules: { ...HEALTHY_DATA.rules, conflicts_total: 0, conflicts_high: 0 },
    };
    renderWithRouter(<HealthDashboard {...baseProps({ data: clean })} />);
    expect(screen.queryByText(/needs attention/i)).not.toBeInTheDocument();
  });

  it("links Review Rules to /app/rules", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    const links = screen.getAllByRole("link", { name: /review rules/i });
    expect(links[0]).toHaveAttribute("href", "/app/rules");
  });

  it("links View History to /app/activity", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByRole("link", { name: /view history/i })).toHaveAttribute("href", "/app/activity");
  });

  it("clicking Review Unclassified calls onReviewUnclassified", () => {
    const onReviewUnclassified = vi.fn();
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA, onReviewUnclassified })} />);
    fireEvent.click(screen.getAllByText(/review unclassified/i)[0]);
    expect(onReviewUnclassified).toHaveBeenCalledTimes(1);
  });

  it("clicking Review Duplicates calls onReviewDuplicates", () => {
    const onReviewDuplicates = vi.fn();
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA, onReviewDuplicates })} />);
    fireEvent.click(screen.getAllByText(/review duplicates/i)[0]);
    expect(onReviewDuplicates).toHaveBeenCalledTimes(1);
  });

  it("clicking Refresh calls onRefresh", () => {
    const onRefresh = vi.fn();
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA, onRefresh })} />);
    fireEvent.click(screen.getByRole("button", { name: /^refresh$/i }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("shows a refreshing state and disables the refresh button", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA, refreshing: true })} />);
    expect(screen.getByRole("button", { name: /refreshing/i })).toBeDisabled();
  });

  it("shows freshness information", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    expect(screen.getByText(/updated/i)).toBeInTheDocument();
  });

  it("shows an unavailable message for files without a fake zero", () => {
    const unavailable = {
      ...HEALTHY_DATA,
      files: { status: "unavailable", message: "File classification health isn't available yet for a connected agent." },
    };
    renderWithRouter(<HealthDashboard {...baseProps({ data: unavailable })} />);
    expect(screen.getByText(/isn't available yet for a connected agent/i)).toBeInTheDocument();
    expect(screen.queryByText(/% classified/)).not.toBeInTheDocument();
  });

  it("shows an unavailable message for duplicates without a fake zero", () => {
    const unavailable = {
      ...HEALTHY_DATA,
      duplicates: { status: "unavailable", message: "Duplicate scanning isn't available yet for a connected agent." },
    };
    renderWithRouter(<HealthDashboard {...baseProps({ data: unavailable })} />);
    expect(screen.getByText(/duplicate scanning isn't available/i)).toBeInTheDocument();
    expect(screen.queryByText("0 groups")).not.toBeInTheDocument();
  });

  it("shows a request-level error state", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ error: "Couldn't load workspace health -- try again." })} />);
    expect(screen.getByText(/couldn't load workspace health/i)).toBeInTheDocument();
  });

  it("shows no eligible files yet when coverage percent is null", () => {
    const empty = {
      ...HEALTHY_DATA,
      files: { status: "available", message: null, scanned: 0, classified: 0, unclassified: 0, errors: 0, classification_coverage_percent: null },
    };
    renderWithRouter(<HealthDashboard {...baseProps({ data: empty })} />);
    expect(screen.getByText(/no eligible files yet/i)).toBeInTheDocument();
  });

  it("offers no destructive action anywhere on the panel", () => {
    renderWithRouter(<HealthDashboard {...baseProps({ data: HEALTHY_DATA })} />);
    for (const forbidden of [/delete/i, /^move$/i, /organize now/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
  });
});
