import { Surface } from "@/components/ui";
import type { DailyActivityPoint } from "@/lib/types";

export function ActivityStrip({ items }: { items: DailyActivityPoint[] }) {
  const maxVolume = Math.max(...items.map((item) => item.total_count), 1);

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-7" data-testid="activity-strip">
      {items.map((item) => {
        const height = `${Math.max(14, (item.total_count / maxVolume) * 92)}px`;
        return (
          <Surface key={`${item.activity_date}-${item.day_label}`} className="dense-surface interactive-card">
            <p className="mono-label text-brand" data-testid="activity-day-label">{item.day_label}</p>
            <div className="mt-4 flex h-24 items-end">
              <div className="w-full border border-line bg-white/5 p-2">
                <div
                  className="bg-brand shadow-[0_0_18px_rgba(0,255,136,0.25)]"
                  style={{ height }}
                />
              </div>
            </div>
            <div className="mt-3 text-xl font-semibold text-ink">{item.total_count}</div>
            <p className="mt-1 text-sm text-slate">{item.risk_count} flagged cases</p>
          </Surface>
        );
      })}
    </div>
  );
}
