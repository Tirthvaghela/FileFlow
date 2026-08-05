import { Link } from "react-router-dom";
import { FolderKanban } from "lucide-react";

export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="marketing flex min-h-dvh items-center justify-center bg-[var(--page)] px-4 py-12">
      <div className="w-full max-w-sm">
        <Link to="/" className="mb-8 flex items-center justify-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--series-1)] text-white">
            <FolderKanban className="h-[18px] w-[18px]" />
          </span>
          <span className="font-display text-base font-semibold text-[var(--text-primary)]">
            FileFlow
          </span>
        </Link>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-8 shadow-2xl shadow-black/30">
          <h1 className="font-display text-xl font-medium text-[var(--text-primary)]">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
