import { Link } from "react-router-dom";
import BrandMark from "../components/BrandMark.jsx";
import RuleOrderPreview from "../components/RuleOrderPreview.jsx";

export default function AuthLayout({ eyebrow, title, subtitle, children }) {
  return (
    <div className="auth-page">
      <aside className="auth-story">
        <Link to="/" className="auth-brand">
          <BrandMark light />
          <span>FileFlow</span>
        </Link>

        <div className="auth-story-copy">
          <h2>Every download, filed where it belongs.</h2>
          <RuleOrderPreview />
        </div>

        <p className="auth-story-note">
          Rules are checked in this order. Keyword first, default last,
          <br className="hidden sm:block" /> and the first match decides the folder.
        </p>
      </aside>

      <main className="auth-form-panel">
        <Link to="/" className="auth-brand auth-mobile-brand">
          <BrandMark light />
          <span>FileFlow</span>
        </Link>

        <section className="auth-form-content">
          {eyebrow && <p className="auth-eyebrow">{eyebrow}</p>}
          <h1>{title}</h1>
          {subtitle && <p className="auth-subtitle">{subtitle}</p>}
          <div className="auth-form">{children}</div>
        </section>
      </main>
    </div>
  );
}
