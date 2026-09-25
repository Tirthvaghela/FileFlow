import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import OrganizePreviewDialog from "./OrganizePreviewDialog.jsx";

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    loading: false,
    waitingForAgent: false,
    error: "",
    preview: null,
    confirming: false,
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };
}

const READY_ITEM = {
  filename: "invoice_august.pdf",
  source_path: "C:/watch/invoice_august.pdf",
  destination_path: "C:/watch/Documents/Invoices/invoice_august.pdf",
  category: "Documents/Invoices",
  action: "moved",
  status: "ready",
  explanation: {
    match_type: "keyword",
    matched_value: "invoice",
    destination: "Documents/Invoices",
    rule_name: 'Keyword "invoice"',
    priority: 1,
  },
  error: null,
};

const DUPLICATE_ITEM = {
  filename: "backup.pdf",
  source_path: "C:/watch/backup.pdf",
  destination_path: "C:/watch/Documents/backup.pdf",
  category: "Documents",
  action: "duplicate_skipped",
  status: "duplicate",
  explanation: null,
  error: null,
};

const NO_MATCH_ITEM = {
  filename: "unknown.xyz",
  source_path: "C:/watch/unknown.xyz",
  destination_path: "C:/watch/Others/unknown.xyz",
  category: "Others",
  action: "moved",
  status: "no_match",
  explanation: { match_type: "default", matched_value: null, destination: "Others", rule_name: null, priority: 9 },
  error: null,
};

const ERROR_ITEM = {
  filename: "broken.pdf",
  source_path: "C:/watch/broken.pdf",
  destination_path: null,
  category: null,
  action: "error",
  status: "error",
  explanation: null,
  error: "Couldn't preview this file -- it may be locked or unreadable.",
};

function previewWith(items) {
  return {
    queued: false,
    command_id: null,
    total: items.length,
    ready: items.filter((i) => i.status === "ready").length,
    duplicates: items.filter((i) => i.status === "duplicate").length,
    no_match: items.filter((i) => i.status === "no_match").length,
    errors: items.filter((i) => i.status === "error").length,
    items,
  };
}

describe("OrganizePreviewDialog", () => {
  it("shows a loading state while the preview is being computed", () => {
    render(<OrganizePreviewDialog {...baseProps({ loading: true })} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders each item's filename and planned destination", () => {
    render(<OrganizePreviewDialog {...baseProps({ preview: previewWith([READY_ITEM]) })} />);

    expect(screen.getByText("invoice_august.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Documents\/Invoices/)).toBeInTheDocument();
  });

  it("renders the Feature 1 explanation for a ready item", () => {
    render(<OrganizePreviewDialog {...baseProps({ preview: previewWith([READY_ITEM]) })} />);

    expect(screen.getByText(/Keyword "invoice"/)).toBeInTheDocument();
  });

  it("distinguishes ready, duplicate, no-match, and error items", () => {
    render(
      <OrganizePreviewDialog
        {...baseProps({
          preview: previewWith([READY_ITEM, DUPLICATE_ITEM, NO_MATCH_ITEM, ERROR_ITEM]),
        })}
      />,
    );

    expect(screen.getByText("Ready to move (1)")).toBeInTheDocument();
    expect(screen.getByText("Skipped (1)")).toBeInTheDocument();
    expect(screen.getByText("No match (1)")).toBeInTheDocument();
    expect(screen.getByText("Errors (1)")).toBeInTheDocument();
    expect(screen.getByText(/couldn't preview this file/i)).toBeInTheDocument();
  });

  it("never fabricates a rule for a no-match item", () => {
    render(<OrganizePreviewDialog {...baseProps({ preview: previewWith([NO_MATCH_ITEM]) })} />);

    expect(screen.getByText(/no matching rule/i)).toBeInTheDocument();
    expect(screen.queryByText(/^why:/i)).not.toBeInTheDocument();
  });

  it("shows correct summary counts computed from the items, not hardcoded", () => {
    render(
      <OrganizePreviewDialog
        {...baseProps({ preview: previewWith([READY_ITEM, DUPLICATE_ITEM, NO_MATCH_ITEM]) })}
      />,
    );

    expect(screen.getByText(/3 total/)).toBeInTheDocument();
    expect(screen.getByText(/1 ready/)).toBeInTheDocument();
    expect(screen.getByText(/1 skipped/)).toBeInTheDocument();
    expect(screen.getByText(/1 no match/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing needs organizing", () => {
    render(<OrganizePreviewDialog {...baseProps({ preview: previewWith([]) })} />);

    expect(screen.getByText(/nothing to organize/i)).toBeInTheDocument();
  });

  it("labels the confirm button with the number of files that will actually be processed", () => {
    // ready + no_match get moved for real; duplicates/errors don't.
    render(
      <OrganizePreviewDialog
        {...baseProps({
          preview: previewWith([READY_ITEM, DUPLICATE_ITEM, NO_MATCH_ITEM, ERROR_ITEM]),
        })}
      />,
    );

    expect(screen.getByRole("button", { name: /organize 2 files/i })).toBeInTheDocument();
  });

  it("disables confirm while nothing is ready or matched", () => {
    render(<OrganizePreviewDialog {...baseProps({ preview: previewWith([DUPLICATE_ITEM]) })} />);

    expect(screen.getByRole("button", { name: /organize 0 files/i })).toBeDisabled();
  });

  it("shows a preview error instead of an item list", () => {
    render(<OrganizePreviewDialog {...baseProps({ error: "Couldn't preview existing files -- try again." })} />);

    expect(screen.getByText(/couldn't preview existing files/i)).toBeInTheDocument();
  });

  it("disables confirm and cancel while an operation is confirming", () => {
    render(
      <OrganizePreviewDialog
        {...baseProps({ preview: previewWith([READY_ITEM]), confirming: true })}
      />,
    );

    expect(screen.getByRole("button", { name: /organizing/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("shows a waiting-for-agent message distinct from the plain loading state", () => {
    render(<OrganizePreviewDialog {...baseProps({ waitingForAgent: true })} />);

    expect(screen.getByText(/waiting for your agent/i)).toBeInTheDocument();
  });
});
