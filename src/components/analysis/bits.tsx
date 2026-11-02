import { Panel } from "@/components/ui/spotlight-card";
import { MorphingSquare } from "@/components/ui/morphing-square";

export const muted = "text-sm text-[#b0bed9]";
export const select = "h-10 rounded-lg border border-input bg-background px-3 text-sm text-foreground [color-scheme:dark]";

export function Spinner({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 text-sm text-[#b0bed9]">
      <MorphingSquare className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "error" | "warn"; children: React.ReactNode }) {
  const tone = kind === "error" ? "border-red-400/30 bg-red-400/10 text-red-200" : kind === "warn" ? "border-amber-400/30 bg-amber-400/10 text-amber-200" : "border-white/10 bg-white/[0.04] text-[#b0bed9]";
  return <p role={kind === "error" ? "alert" : "status"} className={`rounded-lg border p-3 text-sm ${tone}`}>{children}</p>;
}

export function Bar({ value, max = 1, tone = "#8daaff", label }: { value: number; max?: number; tone?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10" role="img" aria-label={label}>
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: tone }} />
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Panel radius={12} className="rounded-xl p-4">
      <p className="text-2xl font-semibold text-white">{value}</p>
      <p className="text-sm text-[#b0bed9]">{label}</p>
      {hint && <p className="mt-1 text-xs text-[#7f8db0]">{hint}</p>}
    </Panel>
  );
}

export const day = (iso: string) => new Date(iso).toISOString().slice(0, 10);
