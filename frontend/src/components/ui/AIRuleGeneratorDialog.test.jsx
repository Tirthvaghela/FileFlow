import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AIRuleGeneratorDialog from "./AIRuleGeneratorDialog.jsx";

const READY_PROPOSAL = {
  rule_type: "keyword",
  name: "GST Invoices",
  keyword: "invoice",
  pattern: null,
  older_than_days: null,
  threshold_mb: null,
  destination: "Finance/Invoices",
};

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    prompt: "",
    onPromptChange: vi.fn(),
    generating: false,
    result: null,
    error: "",
    saving: false,
    impact: null,
    checkingImpact: false,
    onGenerate: vi.fn(),
    onCheckImpact: vi.fn(),
    onEditRequest: vi.fn(),
    onEdit: vi.fn(),
    onReject: vi.fn(),
    onSaveRule: vi.fn(),
    ...overrides,
  };
}

describe("AIRuleGeneratorDialog", () => {
  it("renders the prompt textarea and Generate Rule button", () => {
    render(<AIRuleGeneratorDialog {...baseProps()} />);

    expect(screen.getByPlaceholderText(/put invoices containing gst/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate rule/i })).toBeInTheDocument();
  });

  it("lets the user type a natural-language request", () => {
    const onPromptChange = vi.fn();
    render(<AIRuleGeneratorDialog {...baseProps({ onPromptChange })} />);

    fireEvent.change(screen.getByPlaceholderText(/put invoices containing gst/i), {
      target: { value: "Put invoices into Finance" },
    });

    expect(onPromptChange).toHaveBeenCalledWith("Put invoices into Finance");
  });

  it("Generate Rule is disabled until something is typed", () => {
    render(<AIRuleGeneratorDialog {...baseProps({ prompt: "" })} />);
    expect(screen.getByRole("button", { name: /generate rule/i })).toBeDisabled();
  });

  it("calls onGenerate when Generate Rule is clicked with a non-empty prompt", () => {
    const onGenerate = vi.fn();
    render(<AIRuleGeneratorDialog {...baseProps({ prompt: "Put invoices into Finance", onGenerate })} />);

    fireEvent.click(screen.getByRole("button", { name: /generate rule/i }));

    expect(onGenerate).toHaveBeenCalledTimes(1);
  });

  it("shows a loading state while generating", () => {
    render(<AIRuleGeneratorDialog {...baseProps({ generating: true, prompt: "x" })} />);

    expect(screen.getByText(/interpreting your request/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generating/i })).toBeDisabled();
  });

  it("renders a successful proposal's fields", () => {
    render(
      <AIRuleGeneratorDialog
        {...baseProps({ prompt: "Put invoices into Finance", result: { status: "ready", proposal: READY_PROPOSAL } })}
      />,
    );

    expect(screen.getByText("GST Invoices")).toBeInTheDocument();
    expect(screen.getAllByText(/filename contains "invoice"/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Finance\/Invoices/).length).toBeGreaterThan(0);
  });

  it("renders an unsupported-request response", () => {
    render(
      <AIRuleGeneratorDialog
        {...baseProps({
          result: { status: "unsupported", message: "I can't create a supported FileFlow rule from that." },
        })}
      />,
    );

    expect(screen.getByText(/can't create a supported fileflow rule/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save rule$/i })).not.toBeInTheDocument();
  });

  it("renders a needs-clarification response with its questions", () => {
    render(
      <AIRuleGeneratorDialog
        {...baseProps({
          result: {
            status: "needs_clarification",
            message: "I need more detail.",
            questions: ["What counts as important?", "Where should it go?"],
          },
        })}
      />,
    );

    expect(screen.getByText("I need more detail.")).toBeInTheDocument();
    expect(screen.getByText("What counts as important?")).toBeInTheDocument();
    expect(screen.getByText("Where should it go?")).toBeInTheDocument();
  });

  it("renders a provider failure as an error banner", () => {
    render(
      <AIRuleGeneratorDialog {...baseProps({ error: "AI service is temporarily unavailable." })} />,
    );

    expect(screen.getByText(/ai service is temporarily unavailable/i)).toBeInTheDocument();
  });

  it("clicking Edit calls onEdit with the proposal, not onSaveRule", () => {
    const onEdit = vi.fn();
    const onSaveRule = vi.fn();
    render(
      <AIRuleGeneratorDialog
        {...baseProps({
          result: { status: "ready", proposal: READY_PROPOSAL },
          onEdit,
          onSaveRule,
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));

    expect(onEdit).toHaveBeenCalledWith(READY_PROPOSAL);
    expect(onSaveRule).not.toHaveBeenCalled();
  });

  it("clicking Reject calls onReject without calling onSaveRule", () => {
    const onReject = vi.fn();
    const onSaveRule = vi.fn();
    render(
      <AIRuleGeneratorDialog
        {...baseProps({ result: { status: "ready", proposal: READY_PROPOSAL }, onReject, onSaveRule })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onSaveRule).not.toHaveBeenCalled();
  });

  it("a proposal is never saved just by being rendered -- only an explicit Save Rule click calls onSaveRule", () => {
    const onSaveRule = vi.fn();
    render(
      <AIRuleGeneratorDialog
        {...baseProps({ result: { status: "ready", proposal: READY_PROPOSAL }, onSaveRule })}
      />,
    );

    expect(onSaveRule).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^save rule$/i }));

    expect(onSaveRule).toHaveBeenCalledWith(READY_PROPOSAL);
  });

  it("disables Save Rule and Reject while saving", () => {
    render(
      <AIRuleGeneratorDialog
        {...baseProps({ result: { status: "ready", proposal: READY_PROPOSAL }, saving: true })}
      />,
    );

    expect(screen.getByRole("button", { name: /^saving/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeDisabled();
  });

  it("shows a Check impact affordance for a ready proposal and renders the result", () => {
    const onCheckImpact = vi.fn();
    render(
      <AIRuleGeneratorDialog
        {...baseProps({
          result: { status: "ready", proposal: READY_PROPOSAL },
          onCheckImpact,
          impact: { compared_count: 10, unchanged_count: 8 },
        })}
      />,
    );

    fireEvent.click(screen.getByText(/check impact/i));
    expect(onCheckImpact).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/2 of 10 recent files would be reclassified differently/i)).toBeInTheDocument();
  });
});
