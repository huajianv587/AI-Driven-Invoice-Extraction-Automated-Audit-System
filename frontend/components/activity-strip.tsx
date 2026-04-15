import { Surface } from "@/components/ui";
import type { DailyActivityPoint } from "@/lib/types";

export function ActivityStrip({ items }: { items: DailyActivityPoint[] }) {
  const maxVolume = Math.max(...items.map((item) => item.total_count), 1);

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-7" data-testid="activity-strip">
      {items.map((item) => {
        const height = `${Math.max(14, (item.total_count / maxVolume) * 92)}px`;
        return (
          <Surface key={`${item.activity_date}-${item.day_label}`}>
            <p className="mono-label text-brand" data-testid="activity-day-label">{item.day_label}</p>
            <div className="mt-5 flex h-28 items-end">
              <div className="w-full rounded-[18px] bg-[#eef3ff] p-2">
                <div
                  className="rounded-[14px] bg-gradient-to-b from-brand to-[#5677ff]"
                  style={{ height }}
                />
              </div>
            </div>
            <div className="mt-4 text-2xl font-semibold text-ink">{item.total_count}</div>
            <p className="mt-1 text-sm text-slate">{item.risk_count} flagged cases</p>
          </Surface>
        );
      })}
    </div>
  );
}
