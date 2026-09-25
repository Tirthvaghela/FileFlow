import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ActivityTable from "./ActivityTable.jsx";

function makeLog(overrides = {}) {
  return {
    id: 1,
    final_filename: "report.pdf",
    original_filename: "report.pdf",
    category: "Documents",
    action: "moved",
    destination_path: "C:/watch/Documents/report.pdf",
    timestamp: "2026-01-01T08:00:00Z",
    undone: false,
    ...overrides,
  };
}

function pendingCommand(overrides = {}) {
  return {
    id: 100,
    type: "undo",
    status: "pending",
    success: null,
    error: null,
    result: {},
    log_id: 1,
    created_at: "2026-01-01T08:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

function doneCommand(overrides = {}) {
  return {
    id: 101,
    type: "undo",
    status: "done",
    success: true,
    error: null,
    result: {},
    log_id: 1,
    created_at: "2026-01-01T08:00:00Z",
    completed_at: "2026-01-01T08:00:02Z",
    ...overrides,
  };
}

describe("ActivityTable's per-row agent-command status badge", () => {
  it("shows the existing default badge unchanged when no command matches the row", () => {
    render(<ActivityTable logs={[makeLog()]} showStatusBadge commandStatusByLogId={{}} />);

    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows Waiting for agent… when the matching undo command is pending", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 1: pendingCommand({ type: "undo", log_id: 1 }) }}
      />,
    );

    expect(screen.getByText(/waiting for agent/i)).toBeInTheDocument();
  });

  it("shows Waiting for agent… when the matching reclassify command is pending", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 1: pendingCommand({ type: "reclassify", log_id: 1 }) }}
      />,
    );

    expect(screen.getByText(/waiting for agent/i)).toBeInTheDocument();
  });

  it("shows Completed for a matching completed undo command", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 1: doneCommand({ type: "undo", success: true, log_id: 1 }) }}
      />,
    );

    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows Completed for a matching completed reclassify command", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{
          1: doneCommand({ type: "reclassify", success: true, log_id: 1, result: { destination_path: "C:/watch/Archive/report.pdf" } }),
        }}
      />,
    );

    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows Failed for a matching failed command", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 1: doneCommand({ success: false, error: "disk full", log_id: 1 }) }}
      />,
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("selects the correct command for each row using the real log_id relationship", () => {
    const logs = [makeLog({ id: 1, final_filename: "a.pdf" }), makeLog({ id: 2, final_filename: "b.pdf" })];
    const commandStatusByLogId = {
      1: pendingCommand({ log_id: 1 }),
      2: doneCommand({ success: false, log_id: 2 }),
    };

    render(<ActivityTable logs={logs} showStatusBadge commandStatusByLogId={commandStatusByLogId} />);

    const rowA = screen.getByText("a.pdf").closest("div.flex");
    const rowB = screen.getByText("b.pdf").closest("div.flex");
    expect(rowA.textContent).toMatch(/waiting for agent/i);
    expect(rowB.textContent).toMatch(/failed/i);
  });

  it("an unrelated command for a different log_id does not affect this row", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 999: pendingCommand({ log_id: 999 }) }}
      />,
    );

    // No command matches log_id 1 -- falls back to the existing default,
    // not the unrelated row 999's pending status.
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByText(/waiting for agent/i)).not.toBeInTheDocument();
  });

  it("never fabricates a file count for a matched command with no result data", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{ 1: doneCommand({ type: "undo", result: {}, log_id: 1 }) }}
      />,
    );

    expect(screen.queryByText(/\d+ files?/i)).not.toBeInTheDocument();
  });

  it("renders no token, Authorization header, or raw payload from a matched command", () => {
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{
          1: doneCommand({
            type: "reclassify",
            log_id: 1,
            result: { destination_path: "C:/watch/Archive/report.pdf" },
          }),
        }}
      />,
    );

    const rendered = document.body.textContent;
    expect(rendered).not.toMatch(/bearer/i);
    expect(rendered).not.toMatch(/authorization/i);
    expect(rendered).not.toMatch(/token/i);
  });

  it("existing Undo/Reclassify action buttons still render and dispatch as before", () => {
    const onUndo = () => {};
    const onReclassify = () => {};
    render(
      <ActivityTable
        logs={[makeLog({ id: 1 })]}
        showStatusBadge
        commandStatusByLogId={{}}
        onUndo={onUndo}
        allowAnyRowUndo
        onReclassify={onReclassify}
        categories={["Documents", "Archive"]}
      />,
    );

    expect(screen.getByRole("button", { name: /undo/i })).toBeInTheDocument();
    expect(screen.getByTitle("Move this file to a different category")).toBeInTheDocument();
  });
});

describe("ActivityTable's 'Why?' explanation", () => {
  it("does not show a Why button when the log has no explanation", () => {
    render(<ActivityTable logs={[makeLog()]} />);

    expect(screen.queryByRole("button", { name: /why/i })).not.toBeInTheDocument();
  });

  it("shows a Why button when the log carries an explanation", () => {
    render(
      <ActivityTable
        logs={[
          makeLog({
            explanation: {
              match_type: "keyword",
              matched_value: "invoice",
              destination: "Finance Folder",
              rule_name: 'Keyword "invoice"',
              priority: 1,
            },
          }),
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /why/i })).toBeInTheDocument();
  });

  it("reveals the correct rule, match type, matched value, and destination on click", () => {
    render(
      <ActivityTable
        logs={[
          makeLog({
            explanation: {
              match_type: "keyword",
              matched_value: "invoice",
              destination: "Finance Folder",
              rule_name: 'Keyword "invoice"',
              priority: 1,
            },
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /why/i }));

    expect(screen.getByText('Keyword "invoice"')).toBeInTheDocument();
    expect(screen.getByText("Keyword")).toBeInTheDocument();
    expect(screen.getByText('"invoice"')).toBeInTheDocument();
    expect(screen.getByText("Finance Folder")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("collapses again on a second click", () => {
    render(
      <ActivityTable
        logs={[
          makeLog({
            explanation: { match_type: "extension", matched_value: ".pdf", destination: "Documents", rule_name: 'Extension ".pdf"', priority: 4 },
          }),
        ]}
      />,
    );

    const button = screen.getByRole("button", { name: /why/i });
    fireEvent.click(button);
    expect(screen.getByText('Extension ".pdf"')).toBeInTheDocument();

    fireEvent.click(button);
    expect(screen.queryByText('Extension ".pdf"')).not.toBeInTheDocument();
  });

  it("shows a 'no matching rule' message for a default-category explanation, never fabricating a rule", () => {
    render(
      <ActivityTable
        logs={[
          makeLog({
            explanation: {
              match_type: "default",
              matched_value: null,
              destination: "Others",
              rule_name: null,
              priority: 9,
            },
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /why/i }));

    expect(screen.getByText(/no matching rule/i)).toBeInTheDocument();
  });

  it("renders no raw JSON in the explanation panel", () => {
    render(
      <ActivityTable
        logs={[
          makeLog({
            explanation: {
              match_type: "keyword",
              matched_value: "invoice",
              destination: "Finance Folder",
              rule_name: 'Keyword "invoice"',
              priority: 1,
            },
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /why/i }));

    expect(document.body.textContent).not.toMatch(/[{}]/);
  });
});
