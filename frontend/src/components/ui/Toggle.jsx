export default function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      role="switch"
      aria-checked={checked}
      className={`flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors ${
        checked ? "justify-end" : "justify-start"
      }`}
      style={{ background: checked ? "var(--brand)" : "var(--gridline)" }}
    >
      <span className="h-4 w-4 rounded-full bg-white shadow-sm transition-transform" />
    </button>
  );
}
