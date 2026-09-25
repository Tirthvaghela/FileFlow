import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DuplicateGroupsDialog from "./DuplicateGroupsDialog.jsx";

const GROUP = {
  group_id: "abc123def456",
  duplicate_type: "exact_content_duplicate",
  file_count: 3,
  total_size_bytes: 7340032,
  potential_redundant_bytes: 4890624,
  files: [
    { filename: "invoice.pdf", relative_path: "Finance/invoice.pdf", size_bytes: 2446680, modified_at: "2026-01-10T00:00:00Z", sha256: "a".repeat(64) },
    { filename: "invoice (1).pdf", relative_path: "Downloads/invoice (1).pdf", size_bytes: 2446680, modified_at: "2026-01-12T00:00:00Z", sha256: "a".repeat(64) },
    { filename: "invoice_backup.pdf", relative_path: "Archive/invoice_backup.pdf", size_bytes: 2446680, modified_at: "2026-01-15T00:00:00Z", sha256: "a".repeat(64) },
  ],
};

function resultWith(groups, overrides = {}) {
  return {
    queued: false,
    command_id: null,
    total_files_scanned: 10,
    duplicate_groups: groups.length,
    duplicate_files: groups.reduce((n, g) => n + g.file_count, 0),
    potential_redundant_bytes: groups.reduce((n, g) => n + g.potential_redundant_bytes, 0),
    files_with_errors: 0,
    groups,
    groups_returned: groups.length,
    truncated: false,
    ...overrides,
  };
}

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    loading: false,
    waitingForAgent: false,
    error: "",
    result: null,
    onRefresh: vi.fn(),
    onReviewGroup: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

describe("DuplicateGroupsDialog", () => {
  it("renders the dialog title", () => {
    render(<DuplicateGroupsDialog {...baseProps()} />);
    expect(screen.getByText("Duplicate Files")).toBeInTheDocument();
  });

  it("shows a loading state", () => {
    render(<DuplicateGroupsDialog {...baseProps({ loading: true })} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows a distinct waiting-for-agent state", () => {
    render(<DuplicateGroupsDialog {...baseProps({ waitingForAgent: true })} />);
    expect(screen.getByText(/waiting for your agent/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no duplicates", () => {
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([]) })} />);
    expect(screen.getByText(/no duplicate files found/i)).toBeInTheDocument();
  });

  it("shows a request-level error", () => {
    render(<DuplicateGroupsDialog {...baseProps({ error: "Couldn't check for duplicate files -- try again." })} />);
    expect(screen.getByText(/couldn't check for duplicate files/i)).toBeInTheDocument();
  });

  it("renders the group count and file count summary", () => {
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]) })} />);
    expect(screen.getByText(/1 duplicate group/i)).toBeInTheDocument();
    expect(screen.getByText(/3 duplicate files/i)).toBeInTheDocument();
  });

  it("renders potential redundant storage, formatted", () => {
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]) })} />);
    // Both the overall summary and this single group's own card show the
    // same formatted value.
    expect(screen.getAllByText(/4\.[0-9]+ MB/).length).toBeGreaterThan(0);
  });

  it("renders each file's location within the group card", () => {
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]) })} />);
    expect(screen.getByText(/Finance\/invoice\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/Downloads\/invoice \(1\)\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/Archive\/invoice_backup\.pdf/)).toBeInTheDocument();
  });

  it("shows a files-with-errors notice when present", () => {
    render(
      <DuplicateGroupsDialog
        {...baseProps({ result: resultWith([GROUP], { files_with_errors: 2 }) })}
      />,
    );
    expect(screen.getByText(/2 file\(s\) couldn't be read/i)).toBeInTheDocument();
  });

  it("clicking Review Group calls onReviewGroup with the group and index", () => {
    const onReviewGroup = vi.fn();
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]), onReviewGroup })} />);

    fireEvent.click(screen.getByRole("button", { name: /review group/i }));

    expect(onReviewGroup).toHaveBeenCalledWith(GROUP, 0);
  });

  it("clicking Refresh calls onRefresh, not onClose", () => {
    const onRefresh = vi.fn();
    const onClose = vi.fn();
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]), onRefresh, onClose })} />);

    fireEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("clicking Close calls onClose", () => {
    const onClose = vi.fn();
    render(<DuplicateGroupsDialog {...baseProps({ onClose })} />);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows a truncated notice when the result is capped", () => {
    render(
      <DuplicateGroupsDialog
        {...baseProps({ result: resultWith([GROUP], { duplicate_groups: 50, truncated: true }) })}
      />,
    );
    expect(screen.getByText(/showing the first 1 of 50 groups/i)).toBeInTheDocument();
  });

  it("offers no delete, move, rename, or replace action anywhere", () => {
    render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([GROUP]) })} />);
    for (const forbidden of [/delete/i, /^move$/i, /rename/i, /replace/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
  });

  it("lists two files that share a relative path (same sub-path under two watch folders) without a duplicate-key warning", () => {
    const sameSubPathTwice = {
      ...GROUP,
      file_count: 2,
      files: [
        { ...GROUP.files[0], relative_path: "Finance/invoice.pdf" },
        { ...GROUP.files[0], relative_path: "Finance/invoice.pdf" },
      ],
    };
    const errorSpy = vi.spyOn(console, "error");
    try {
      render(<DuplicateGroupsDialog {...baseProps({ result: resultWith([sameSubPathTwice]) })} />);

      expect(screen.getAllByText(/Finance\/invoice\.pdf/)).toHaveLength(2);
      expect(errorSpy.mock.calls.filter((args) => /same key/i.test(String(args[0])))).toEqual([]);
    } finally {
      errorSpy.mockRestore();
    }
  });
});
