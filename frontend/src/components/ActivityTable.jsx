import { useEffect, useRef, useState } from "react";
import FileBadge from "./FileBadge.jsx";
import HighlightName from "./HighlightName.jsx";
import ExplanationPanel from "./ExplanationPanel.jsx";
import Stamp from "./ui/Stamp.jsx";
import FolderTag from "./ui/FolderTag.jsx";
import { stampFor, UNDOABLE_ACTIONS } from "../utils/activity.js";
import { pad2, tierFor } from "../utils/ruleTiers.js";

function rowTime(iso) {
  const d = new Date(iso);
  const date = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${date} ${time}`;
}

// commandStatusByLogId correlates this row's log.id with the most recent
// undo/reclassify agent command it triggered (useCommandStatusByLogId.js).
// Only shown when such a command exists -- a row with no agent command
// has no agent status to report. success===false specifically means the
// command finished with a real failure, distinct from still pending.
function agentCommandStatus(command) {
  if (!command) return null;
  if (command.status === "pending") return { label: "Waiting for agent…", color: "var(--warn)" };
  if (command.success === false) return { label: "Failed", color: "var(--stamp)" };
  return { label: "Completed", color: "var(--filed)" };
}

// v5 Activity ledger: rows separated by 1px --rule under a 1px ink top
// rule. time · file (marked term) → folder · stamp · tier chip · agent
// status · Why here? / Undo / Move to…
export default function ActivityTable({
  logs,
  onUndo,
  undoing = false,
  undoingId = null,
  allowAnyRowUndo = false,
  showStatusBadge = false,
  commandStatusByLogId = {},
  onReclassify,
  categories = [],
  openId = null,
  emptyMessage = "No activity yet — drop a file into the watched folder to see it here.",
}) {
  const [expandedId, setExpandedId] = useState(openId);
  const openRef = useRef(null);

  useEffect(() => {
    if (openId == null) return;
    setExpandedId(openId);
  }, [openId]);

  useEffect(() => {
    if (openId != null && openRef.current?.scrollIntoView) {
      openRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [openId, logs.length]);

  if (!logs.length) {
    return (
      <div className="border-t border-[var(--ink)] px-1 py-10">
        <p className="m-0 text-[13px] text-[var(--ink-muted)]">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div role="table" aria-label="Activity" className="flex flex-col border-t border-[var(--ink)]">
      {logs.map((log, i) => {
        const expanded = expandedId === log.id;
        const stamp = stampFor(log);
        const tier = tierFor(log.explanation?.match_type);
        const agent = showStatusBadge ? agentCommandStatus(commandStatusByLogId[log.id]) : null;
        const canUndo =
          onUndo && !log.undone && (allowAnyRowUndo ? UNDOABLE_ACTIONS.includes(log.action) : i === 0);
        const busy = allowAnyRowUndo ? undoingId === log.id : undoing;
        return (
          <div
            key={log.id}
            role="row"
            ref={log.id === openId ? openRef : null}
            className="border-b border-[var(--rule)] transition-colors"
            style={{ background: expanded ? "var(--sheet-2)" : "transparent", transitionDuration: "var(--d2)" }}
          >
            <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2 px-1 py-3">
              <span className="shrink-0 basis-[92px] font-mono-data text-[11.5px] font-medium text-[var(--ink-muted)]">
                {rowTime(log.timestamp)}
              </span>
              <span className="flex min-w-0 flex-[1_1_300px] items-center gap-2.5">
                <FileBadge filename={log.final_filename} size="sm" />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <HighlightName
                    name={log.final_filename}
                    term={log.explanation?.matched_value}
                    className={`font-mono-data text-[12.5px] font-medium ${log.undone ? "line-through" : ""}`}
                  />
                  <span className="text-[12px] leading-[1.7] text-[var(--ink-2)]">
                    {log.action === "duplicate_skipped" ? "already in " : "→ "}
                    <FolderTag>{log.category}</FolderTag>
                  </span>
                </span>
              </span>
              <Stamp tone={stamp.tone}>{stamp.label}</Stamp>
              {tier && (
                <span
                  title="Rule tier that decided"
                  className="shrink-0 rounded-[2px] border border-[var(--rule-2)] px-[5px] py-[2px] font-mono-data text-[10.5px] font-semibold text-[var(--ink-2)]"
                >
                  T{pad2(tier.n)}
                </span>
              )}
              {agent && (
                <span
                  title="Remote agent command status"
                  className="whitespace-nowrap font-mono-data text-[11px]"
                  style={{ color: agent.color }}
                >
                  agent: <span>{agent.label}</span>
                </span>
              )}
              <span className="ml-auto flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setExpandedId(expanded ? null : log.id)}
                  aria-expanded={expanded}
                  aria-label={`Why was ${log.final_filename} placed here?`}
                  className="ff-btn ff-btn-tertiary ff-btn-sm"
                >
                  {expanded ? "Hide why" : "Why here?"}
                </button>
                {canUndo && (
                  <button type="button" onClick={() => onUndo(log)} disabled={busy} className="ff-btn ff-btn-outline ff-btn-sm">
                    {busy ? "Undoing…" : "Undo"}
                  </button>
                )}
                {onReclassify && log.destination_path && !log.undone && (
                  <select
                    value=""
                    onChange={(e) => {
                      if (e.target.value) onReclassify(log, e.target.value);
                    }}
                    title="Move this file to a different category"
                    aria-label={`Move ${log.final_filename} to another folder`}
                    className="ff-input h-[30px] max-w-[130px] text-[12px]"
                  >
                    <option value="">Move to…</option>
                    {categories
                      .filter((c) => c !== log.category)
                      .map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                  </select>
                )}
              </span>
            </div>
            {expanded && (
              <div className="mx-1 mb-3.5">
                <ExplanationPanel explanation={log.explanation} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
