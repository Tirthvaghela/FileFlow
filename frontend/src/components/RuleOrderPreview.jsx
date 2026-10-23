const RULES = [
  "Keyword",
  "Regex",
  "Content keyword",
  "Extension",
  "Large file",
  "File age",
  "Category",
  "Automatic",
  "Default",
];

export default function RuleOrderPreview({ className = "" }) {
  return (
    <ol className={`rule-order ${className}`}>
      {RULES.map((rule, index) => (
        <li
          key={rule}
          className={index === 0 ? "rule-order-primary" : ""}
          style={{ "--rule-indent": `${index * 14}px` }}
        >
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{rule}</strong>
        </li>
      ))}
    </ol>
  );
}
