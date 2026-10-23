// Section label followed by a flex-1 dashed rule, with an optional
// right-aligned slot (a link, a date range, a count).
export default function Kicker({ children, right = null, as: Tag = "span", className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <Tag className="ff-kicker m-0 shrink-0">{children}</Tag>
      <span aria-hidden="true" className="flex-1 border-t border-dashed border-[var(--rule-2)]" />
      {right}
    </div>
  );
}
