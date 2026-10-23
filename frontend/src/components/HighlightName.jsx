// A filename with the term that decided its folder marked, e.g.
// "<mark>invoice</mark>_jan.pdf". Only marks a term that really occurs in
// the name (case-insensitive); otherwise renders the plain name.
export default function HighlightName({ name, term, className = "", title }) {
  const t = typeof term === "string" ? term.trim() : "";
  const idx = t ? name.toLowerCase().indexOf(t.toLowerCase()) : -1;
  if (idx < 0) {
    return (
      <span className={className} title={title}>
        {name}
      </span>
    );
  }
  return (
    <span className={className} title={title ?? name}>
      {name.slice(0, idx)}
      <mark className="ff-mark">{name.slice(idx, idx + t.length)}</mark>
      {name.slice(idx + t.length)}
    </span>
  );
}
