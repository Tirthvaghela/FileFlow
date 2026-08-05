export default function EmptyState({ message }) {
  return (
    <div className="flex h-[260px] items-center justify-center text-sm text-[var(--text-muted)]">
      {message}
    </div>
  );
}
