import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FileSearchDialog from "./FileSearchDialog.jsx";

const READY_RESULT = {
  status: "ready",
  message: null,
  questions: [],
  interpretation: ['Filename contains "invoice"', "Extension is .pdf", "Modified during August 2026"],
  queued: false,
  command_id: null,
  total_files_scanned: 10,
  files_with_errors: 0,
  total_matches: 1,
  returned: 1,
  truncated: false,
  results: [
    {
      filename: "invoice_august.pdf",
      relative_path: "Finance/Invoices/invoice_august.pdf",
      extension: ".pdf",
      size_bytes: 2446680,
      modified_at: "2026-08-18T00:00:00Z",
      category: "Finance/Invoices",
      match_reasons: ['Filename contains "invoice"', "Extension is .pdf", "Modified during August 2026"],
    },
  ],
};

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    prompt: "",
    onPromptChange: vi.fn(),
    searching: false,
    waitingForAgent: false,
    result: null,
    error: "",
    onSearch: vi.fn(),
    onClear: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

describe("FileSearchDialog", () => {
  it("renders the dialog title and input", () => {
    render(<FileSearchDialog {...baseProps()} />);
    expect(screen.getByText("Search your files")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/find pdf invoices from august/i)).toBeInTheDocument();
  });

  it("Search button is disabled with an empty prompt", () => {
    render(<FileSearchDialog {...baseProps({ prompt: "" })} />);
    expect(screen.getByRole("button", { name: /^search$/i })).toBeDisabled();
  });

  it("submitting the form calls onSearch", () => {
    const onSearch = vi.fn();
    render(<FileSearchDialog {...baseProps({ prompt: "find invoices", onSearch })} />);

    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("shows a loading state while searching", () => {
    render(<FileSearchDialog {...baseProps({ searching: true })} />);
    expect(screen.getAllByText(/^searching…$/i).length).toBeGreaterThan(0);
  });

  it("shows a distinct waiting-for-agent state", () => {
    render(<FileSearchDialog {...baseProps({ waitingForAgent: true })} />);
    expect(screen.getByText(/waiting for your agent/i)).toBeInTheDocument();
  });

  it("renders the interpretation checklist", () => {
    render(<FileSearchDialog {...baseProps({ result: READY_RESULT })} />);
    expect(screen.getByText(/search interpretation/i)).toBeInTheDocument();
    expect(screen.getByText(/✓ Extension is \.pdf/)).toBeInTheDocument();
  });

  it("renders search results with metadata and match reasons", () => {
    render(<FileSearchDialog {...baseProps({ result: READY_RESULT })} />);
    expect(screen.getByText("invoice_august.pdf")).toBeInTheDocument();
    expect(screen.getByText("Finance/Invoices/invoice_august.pdf")).toBeInTheDocument();
    expect(screen.getAllByText(/Filename contains "invoice"/).length).toBeGreaterThan(0);
  });

  it("shows an empty result state", () => {
    render(
      <FileSearchDialog
        {...baseProps({ result: { ...READY_RESULT, total_matches: 0, returned: 0, results: [] } })}
      />,
    );
    expect(screen.getByText(/no files matched your search/i)).toBeInTheDocument();
  });

  it("shows an unsupported state", () => {
    render(
      <FileSearchDialog
        {...baseProps({
          result: {
            status: "unsupported",
            message: "This search needs an understanding of what's inside the file.",
            questions: [],
            interpretation: [],
          },
        })}
      />,
    );
    expect(screen.getByText(/understanding of what's inside the file/i)).toBeInTheDocument();
  });

  it("shows a needs-clarification state with questions", () => {
    render(
      <FileSearchDialog
        {...baseProps({
          result: {
            status: "needs_clarification",
            message: "Which date range do you mean?",
            questions: ["Which date range do you mean by 'recently'?"],
            interpretation: [],
          },
        })}
      />,
    );
    expect(screen.getByText(/which date range do you mean\?/i)).toBeInTheDocument();
    expect(screen.getByText(/which date range do you mean by 'recently'\?/i)).toBeInTheDocument();
  });

  it("shows a provider error state", () => {
    render(<FileSearchDialog {...baseProps({ error: "AI search interpretation is temporarily unavailable." })} />);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
  });

  it("shows a truncation message", () => {
    render(
      <FileSearchDialog
        {...baseProps({ result: { ...READY_RESULT, total_matches: 50, returned: 1, truncated: true } })}
      />,
    );
    expect(screen.getByText(/showing the first 1 of 50 results/i)).toBeInTheDocument();
  });

  it("clicking Clear Search calls onClear", () => {
    const onClear = vi.fn();
    render(<FileSearchDialog {...baseProps({ onClear })} />);

    fireEvent.click(screen.getByRole("button", { name: /clear search/i }));

    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("clicking Close calls onClose", () => {
    const onClose = vi.fn();
    render(<FileSearchDialog {...baseProps({ onClose })} />);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("never exposes an absolute filesystem path", () => {
    render(<FileSearchDialog {...baseProps({ result: READY_RESULT })} />);
    expect(screen.queryByText(/C:\\/)).not.toBeInTheDocument();
  });

  it("offers no organize, delete, move, or rule-creation action", () => {
    render(<FileSearchDialog {...baseProps({ result: READY_RESULT })} />);
    for (const forbidden of [/organize/i, /delete/i, /^move$/i, /create rule/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
  });

  it("shows two results that share a relative path (same sub-path under two watch folders) without a duplicate-key warning", () => {
    const item = READY_RESULT.results[0];
    const result = { ...READY_RESULT, total_matches: 2, returned: 2, results: [item, { ...item, size_bytes: 1024 }] };
    const errorSpy = vi.spyOn(console, "error");
    try {
      render(<FileSearchDialog {...baseProps({ result })} />);

      expect(screen.getAllByText("Finance/Invoices/invoice_august.pdf")).toHaveLength(2);
      expect(errorSpy.mock.calls.filter((args) => /same key/i.test(String(args[0])))).toEqual([]);
    } finally {
      errorSpy.mockRestore();
    }
  });
});
