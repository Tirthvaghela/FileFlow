import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import ChartTooltip from "./ChartTooltip.jsx";
import EmptyState from "./EmptyState.jsx";

function formatShortDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
  });
}

export default function WeeklyChart({ data }) {
  const hasActivity = data.some((d) => d.count > 0);
  if (!hasActivity) {
    return <EmptyState message="No activity in the last 7 days" />;
  }

  const lastIndex = data.length - 1;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 24, right: 8, left: 8, bottom: 8 }} barCategoryGap="28%">
        <XAxis
          dataKey="date"
          tickFormatter={formatShortDate}
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
        />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: "var(--gridline)" }}
        />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={40}>
          <LabelList
            dataKey="count"
            position="top"
            fill="var(--text-secondary)"
            fontSize={12}
            fontWeight={600}
            offset={8}
          />
          {data.map((d, i) => (
            <Cell
              key={d.date}
              fill="var(--series-1)"
              fillOpacity={i === lastIndex ? 1 : 0.18}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
