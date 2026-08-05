import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import EmptyState from "./EmptyState.jsx";
import { buildCategoryColorMap } from "../utils/categoryMeta.js";

function DonutTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { name, value } = payload[0];
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2 text-sm shadow-sm">
      <p className="font-medium text-[var(--text-primary)]">{name}</p>
      <p className="text-[var(--text-secondary)]">{value} files</p>
    </div>
  );
}

const MAX_SLICES = 6;

// Real rule-driven categories can grow well past what a legend can show
// cleanly, so the smallest tail folds into "Other" -- the underlying counts
// are still real, just grouped for readability.
function groupTopCategories(data) {
  if (data.length <= MAX_SLICES) return data;
  const byCount = [...data].sort((a, b) => b.count - a.count);
  const top = byCount.slice(0, MAX_SLICES - 1);
  const rest = byCount.slice(MAX_SLICES - 1);
  const otherCount = rest.reduce((sum, d) => sum + d.count, 0);
  return [...top, { category: "Other", count: otherCount }];
}

export default function CategoryDonut({ data }) {
  if (!data.length) {
    return <EmptyState message="No files organized yet" />;
  }

  const grouped = groupTopCategories(data);
  const total = grouped.reduce((sum, d) => sum + d.count, 0);
  const colorMap = buildCategoryColorMap(grouped.filter((d) => d.category !== "Other").map((d) => d.category));
  colorMap.Other = "var(--text-muted)";
  const sorted = [...grouped].sort((a, b) => {
    if (a.category === "Other") return 1;
    if (b.category === "Other") return -1;
    return b.count - a.count;
  });

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
      <div className="relative h-[220px] w-[220px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={sorted}
              dataKey="count"
              nameKey="category"
              innerRadius={64}
              outerRadius={100}
              startAngle={90}
              endAngle={-270}
              paddingAngle={sorted.length > 1 ? 1.5 : 0}
              stroke="var(--surface-1)"
              strokeWidth={2}
            >
              {sorted.map((d) => (
                <Cell key={d.category} fill={colorMap[d.category]} />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold text-[var(--text-primary)]">
            {total.toLocaleString()}
          </span>
          <span className="text-xs text-[var(--text-muted)]">total files</span>
        </div>
      </div>

      <div className="w-full space-y-2">
        {sorted.map((d) => (
          <div key={d.category} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-[var(--text-secondary)]">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: colorMap[d.category] }}
              />
              {d.category}
            </span>
            <span className="text-[var(--text-muted)]">
              {total ? Math.round((d.count / total) * 100) : 0}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
