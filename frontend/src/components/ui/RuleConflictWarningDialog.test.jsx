import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RuleConflictWarningDialog from "./RuleConflictWarningDialog.jsx";

const PRECEDENCE_CONFLICT = {
  severity: "warning",
  type: "precedence_overlap",
  rules: [
    { rule_type: "keyword", description: 'Keyword "invoice"', destination: "Finance/Invoices" },
    { rule_type: "extension", description: 'Extension ".pdf"', destination: "Documents/PDF" },
  ],
  example: { filename: "invoice.pdf", destination: "Finance/Invoices", winning_rule: 'Keyword "invoice"' },
  message: "Both rules can match invoice.pdf. Keyword rules are evaluated before extension rules.",
};

const SHADOW_CONFLICT = {
  severity: "high",
  type: "shadowed_rule",
  rules: [
    { rule_type: "keyword", description: 'Keyword "receipt"', destination: "Finance/Receipts" },
    { rule_type: "keyword", description: 'Keyword "gstreceipt"', destination: "Finance/GST" },
  ],
  example: null,
  message: '"Keyword \\"gstreceipt\\"" can never take effect.',
};

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    conflicts: [PRECEDENCE_CONFLICT],
    saving: false,
    onBack: vi.fn(),
    onSaveAnyway: vi.fn(),
    ...overrides,
  };
}

describe("RuleConflictWarningDialog", () => {
  it("renders the dialog title", () => {
    render(<RuleConflictWarningDialog {...baseProps()} />);
    expect(screen.getByText("Rule Conflict Detected")).toBeInTheDocument();
  });

  it("renders each conflict's participating rules", () => {
    render(<RuleConflictWarningDialog {...baseProps()} />);
    expect(screen.getAllByText(/Keyword "invoice"/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Extension "\.pdf"/)).toBeInTheDocument();
  });

  it("renders the example filename and winning destination", () => {
    render(<RuleConflictWarningDialog {...baseProps()} />);
    expect(screen.getByText("invoice.pdf")).toBeInTheDocument();
    expect(screen.getByText("Finance/Invoices")).toBeInTheDocument();
  });

  it("renders a conflict with no example gracefully", () => {
    render(<RuleConflictWarningDialog {...baseProps({ conflicts: [SHADOW_CONFLICT] })} />);
    expect(screen.getByText(/can never take effect/)).toBeInTheDocument();
  });

  it("renders multiple conflicts", () => {
    render(<RuleConflictWarningDialog {...baseProps({ conflicts: [PRECEDENCE_CONFLICT, SHADOW_CONFLICT] })} />);
    expect(screen.getAllByText(/Keyword "invoice"/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Keyword "gstreceipt"/)).toBeInTheDocument();
  });

  it("clicking Back & Edit calls onBack, not onSaveAnyway", () => {
    const onBack = vi.fn();
    const onSaveAnyway = vi.fn();
    render(<RuleConflictWarningDialog {...baseProps({ onBack, onSaveAnyway })} />);

    fireEvent.click(screen.getByRole("button", { name: /back & edit/i }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onSaveAnyway).not.toHaveBeenCalled();
  });

  it("clicking Save Anyway calls onSaveAnyway, not onBack", () => {
    const onBack = vi.fn();
    const onSaveAnyway = vi.fn();
    render(<RuleConflictWarningDialog {...baseProps({ onBack, onSaveAnyway })} />);

    fireEvent.click(screen.getByRole("button", { name: /save anyway/i }));

    expect(onSaveAnyway).toHaveBeenCalledTimes(1);
    expect(onBack).not.toHaveBeenCalled();
  });

  it("disables both buttons while saving", () => {
    render(<RuleConflictWarningDialog {...baseProps({ saving: true })} />);
    expect(screen.getByRole("button", { name: /back & edit/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
  });

  it("shows Saving… label while saving", () => {
    render(<RuleConflictWarningDialog {...baseProps({ saving: true })} />);
    expect(screen.getByRole("button", { name: /^saving…$/i })).toBeInTheDocument();
  });

  it("does not save automatically just by being opened", () => {
    const onSaveAnyway = vi.fn();
    render(<RuleConflictWarningDialog {...baseProps({ onSaveAnyway })} />);
    expect(onSaveAnyway).not.toHaveBeenCalled();
  });
});
