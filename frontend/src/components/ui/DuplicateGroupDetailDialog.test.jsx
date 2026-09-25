import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DuplicateGroupDetailDialog from "./DuplicateGroupDetailDialog.jsx";

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

function baseProps(overrides = {}) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    group: GROUP,
    groupNumber: 7,
    onClose: vi.fn(),
    ...overrides,
  };
}

describe("DuplicateGroupDetailDialog", () => {
  it("renders the group number", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText("Duplicate Group #7")).toBeInTheDocument();
  });

  it("renders the duplicate type label", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText("Exact content duplicates")).toBeInTheDocument();
  });

  it("renders every file with its location", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText("invoice.pdf")).toBeInTheDocument();
    expect(screen.getByText("Finance/invoice.pdf")).toBeInTheDocument();
    expect(screen.getByText("invoice (1).pdf")).toBeInTheDocument();
    expect(screen.getByText("Downloads/invoice (1).pdf")).toBeInTheDocument();
    expect(screen.getByText("invoice_backup.pdf")).toBeInTheDocument();
    expect(screen.getByText("Archive/invoice_backup.pdf")).toBeInTheDocument();
  });

  it("explains the SHA-256 match", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText(/all 3 files have identical sha-256 content hashes/i)).toBeInTheDocument();
  });

  it("shows potential redundant storage, formatted", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText(/4\.[0-9]+ MB/)).toBeInTheDocument();
  });

  it("shows the no-files-deleted confirmation", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    expect(screen.getByText("No files have been deleted.")).toBeInTheDocument();
  });

  it("renders nothing when there is no group", () => {
    const { container } = render(<DuplicateGroupDetailDialog {...baseProps({ group: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("clicking Close calls onClose", () => {
    const onClose = vi.fn();
    render(<DuplicateGroupDetailDialog {...baseProps({ onClose })} />);

    fireEvent.click(screen.getByRole("button", { name: /^close$/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("offers no delete, move, rename, or replace action", () => {
    render(<DuplicateGroupDetailDialog {...baseProps()} />);
    for (const forbidden of [/delete/i, /^move$/i, /rename/i, /replace/i, /keep/i]) {
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
      render(<DuplicateGroupDetailDialog {...baseProps({ group: sameSubPathTwice })} />);

      expect(screen.getAllByText("Finance/invoice.pdf")).toHaveLength(2);
      expect(errorSpy.mock.calls.filter((args) => /same key/i.test(String(args[0])))).toEqual([]);
    } finally {
      errorSpy.mockRestore();
    }
  });
});
