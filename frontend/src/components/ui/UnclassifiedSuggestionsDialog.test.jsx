import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import UnclassifiedSuggestionsDialog from "./UnclassifiedSuggestionsDialog.jsx";

const READY_SUGGESTION = {
  group_key: "mystery",
  file_names: ["mystery_file.xyz"],
  files_affected: 1,
  suggestion_status: "ready",
  suggested_category: "Invoices",
  suggested_destination: "Finance/Invoices",
  reason: ['Filename contains "invoice"', "Small file"],
  suggested_rule: {
    rule_type: "keyword",
    name: "Invoices",
    keyword: "invoice",
    pattern: null,
    older_than_days: null,
    threshold_mb: null,
    destination: "Finance/Invoices",
  },
  message: null,
};

const GROUPED_SUGGESTION = {
  ...READY_SUGGESTION,
  group_key: "receipt",
  file_names: ["receipt_1.pdf", "receipt_2.pdf", "receipt_3.pdf"],
  files_affected: 3,
};

const NEEDS_CLARIFICATION_SUGGESTION = {
  group_key: "vague",
  file_names: ["file123.xyz"],
  files_affected: 1,
  suggestion_status: "needs_clarification",
  suggested_category: null,
  suggested_destination: null,
  reason: [],
  suggested_rule: null,
  message: "Filename and extension don't provide enough information to suggest a rule.",
};

const UNSUPPORTED_SUGGESTION = {
  group_key: "weird",
  file_names: ["weird_thing.bin"],
  files_affected: 1,
  suggestion_status: "unsupported",
  suggested_category: null,
  suggested_destination: null,
  reason: [],
  suggested_rule: null,
  message: "No supported FileFlow rule type fits these files.",
};

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    loading: false,
    waitingForAgent: false,
    error: "",
    result: null,
    ignoredKeys: new Set(),
    creatingKey: null,
    onCreateRule: vi.fn(),
    onIgnore: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

function resultWith(suggestions, overrides = {}) {
  return {
    queued: false,
    command_id: null,
    total: suggestions.length,
    unclassified: suggestions.length,
    suggestions,
    batch_limited: false,
    message: null,
    ...overrides,
  };
}

describe("UnclassifiedSuggestionsDialog", () => {
  it("renders the dialog title", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps()} />);
    expect(screen.getByText("AI Suggestions")).toBeInTheDocument();
  });

  it("shows a loading state while suggestions are being generated", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ loading: true })} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows a distinct waiting-for-agent state", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ waitingForAgent: true })} />);
    expect(screen.getByText(/waiting for your agent/i)).toBeInTheDocument();
  });

  it("renders a suggestion's filename", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([READY_SUGGESTION]) })} />);
    expect(screen.getByText("mystery_file.xyz")).toBeInTheDocument();
  });

  it("renders the suggested destination", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([READY_SUGGESTION]) })} />);
    expect(screen.getByText(/Finance\/Invoices/)).toBeInTheDocument();
  });

  it("renders the suggested rule's plain-language condition", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([READY_SUGGESTION]) })} />);
    expect(screen.getAllByText(/filename contains "invoice"/i).length).toBeGreaterThan(0);
  });

  it("renders the reasoning bullets", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([READY_SUGGESTION]) })} />);
    expect(screen.getByText("Small file")).toBeInTheDocument();
  });

  it("shows how many files a grouped suggestion covers", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([GROUPED_SUGGESTION]) })} />);
    expect(screen.getByText("receipt_1.pdf")).toBeInTheDocument();
    expect(screen.getByText(/\+ 2 more/)).toBeInTheDocument();
  });

  it("renders a needs-clarification suggestion without a Create Rule button", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({ result: resultWith([NEEDS_CLARIFICATION_SUGGESTION]) })}
      />,
    );

    expect(screen.getByText(/don't provide enough information/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create rule/i })).not.toBeInTheDocument();
  });

  it("renders an unsupported suggestion without a Create Rule button", () => {
    render(
      <UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([UNSUPPORTED_SUGGESTION]) })} />,
    );

    expect(screen.getByText(/no supported fileflow rule type/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create rule/i })).not.toBeInTheDocument();
  });

  it("shows a provider-unavailable message distinct from the loading/empty states", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({
          result: resultWith([], {
            unclassified: 2,
            message: "AI service is temporarily unavailable. Please try again shortly.",
          }),
        })}
      />,
    );

    expect(screen.getByText(/ai service is temporarily unavailable/i)).toBeInTheDocument();
    // A whole-batch provider failure produced no suggestions at all -- it
    // must not also claim the user "dismissed" any (real-browser smoke test
    // finding: both messages rendered together).
    expect(screen.queryByText(/all suggestions dismissed/i)).not.toBeInTheDocument();
  });

  it("still says all suggestions were dismissed once the user ignores every real one", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({
          result: resultWith([UNSUPPORTED_SUGGESTION], { unclassified: 1 }),
          ignoredKeys: new Set([UNSUPPORTED_SUGGESTION.group_key]),
        })}
      />,
    );

    expect(screen.getByText(/all suggestions dismissed/i)).toBeInTheDocument();
  });

  it("shows a network/request-level error", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ error: "Couldn't get AI suggestions -- try again." })} />);
    expect(screen.getByText(/couldn't get ai suggestions/i)).toBeInTheDocument();
  });

  it("shows an empty state when nothing is unclassified", () => {
    render(<UnclassifiedSuggestionsDialog {...baseProps({ result: resultWith([], { unclassified: 0 }) })} />);
    expect(screen.getByText(/nothing unclassified right now/i)).toBeInTheDocument();
  });

  it("clicking Create Rule calls onCreateRule with the suggestion, not automatically on render", () => {
    const onCreateRule = vi.fn();
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({ result: resultWith([READY_SUGGESTION]), onCreateRule })}
      />,
    );

    expect(onCreateRule).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /create rule/i }));
    expect(onCreateRule).toHaveBeenCalledWith(READY_SUGGESTION);
  });

  it("clicking Ignore calls onIgnore with the suggestion, not onCreateRule", () => {
    const onIgnore = vi.fn();
    const onCreateRule = vi.fn();
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({ result: resultWith([READY_SUGGESTION]), onIgnore, onCreateRule })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^ignore$/i }));

    expect(onIgnore).toHaveBeenCalledWith(READY_SUGGESTION);
    expect(onCreateRule).not.toHaveBeenCalled();
  });

  it("a suggestion in ignoredKeys is not rendered", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({
          result: resultWith([READY_SUGGESTION]),
          ignoredKeys: new Set(["mystery"]),
        })}
      />,
    );

    expect(screen.queryByText("mystery_file.xyz")).not.toBeInTheDocument();
  });

  it("disables Create Rule and Ignore while a different suggestion is being created", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({ result: resultWith([READY_SUGGESTION]), creatingKey: "some-other-group" })}
      />,
    );

    expect(screen.getByRole("button", { name: /create rule/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^ignore$/i })).toBeDisabled();
  });

  it("shows Creating… on the specific suggestion being saved", () => {
    render(
      <UnclassifiedSuggestionsDialog
        {...baseProps({ result: resultWith([READY_SUGGESTION]), creatingKey: "mystery" })}
      />,
    );

    expect(screen.getByRole("button", { name: /creating/i })).toBeInTheDocument();
  });

  it("clicking Close calls onClose", () => {
    const onClose = vi.fn();
    render(<UnclassifiedSuggestionsDialog {...baseProps({ onClose })} />);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
