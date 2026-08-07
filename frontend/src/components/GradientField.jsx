export default function GradientField({ className = "" }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <div className="absolute -top-24 left-[8%] h-[380px] w-[380px] rounded-full bg-[var(--brand)]/8 blur-[110px] animate-drift-slow" />
      <div className="absolute top-[10%] right-[5%] h-[320px] w-[320px] rounded-full bg-[var(--series-1)]/8 blur-[110px] animate-drift-slower" />
      <div className="absolute bottom-[-10%] left-[30%] h-[300px] w-[300px] rounded-full bg-[var(--series-6)]/8 blur-[100px] animate-drift-slow" />
    </div>
  );
}
