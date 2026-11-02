import "@/components/ui/weather.css";
import { Weather } from "@/components/ui/weather";
import { Bar, day, muted } from "@/components/analysis/bits";
import { buildWeatherProps } from "@/lib/weather-map";
import { Panel } from "@/components/ui/spotlight-card";
import { cloudOutlook } from "@/lib/cloud-outlook";
import type { Forecast } from "@/lib/analysis-api";

const TONE = { good: "#6ee7b7", fair: "#fcd34d", poor: "#fca5a5", unknown: "#64748b" } as const;
const weekday = (date: string) => new Date(`${date}T12:00:00Z`).toLocaleDateString("en", { weekday: "short", timeZone: "UTC" });

/** The forecast, plus the answer an Earth-observation user really wants: when will the sky be clear? */
export function WeatherPanel({ forecast, place }: { forecast: Forecast; place: string }) {
  const outlook = cloudOutlook(forecast);
  const widget = buildWeatherProps(forecast, place);
  const best = outlook.filter((d) => d.avg != null).sort((a, b) => (a.avg as number) - (b.avg as number))[0];
  return (
    <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
      <div className="flex flex-col items-center gap-2">
        <Weather {...widget} />
        <p className="max-w-[360px] text-center text-xs text-[#7f8db0]">
          <a href={forecast.source.url} target="_blank" rel="noreferrer" className="underline">{forecast.source.attribution}</a> (CC BY 4.0). Model forecast, not a measurement.
        </p>
      </div>
      <Panel as="section" aria-label="Satellite clarity outlook">
        <h3 className="text-lg font-semibold text-white">Satellite clarity outlook</h3>
        <p className={muted}>Forecast cloud cover around 09:00-12:00 local time, when Sentinel-2 usually passes. Low cloud means a clearer new picture.</p>
        <ul className="mt-4 space-y-3">
          {outlook.map((d) => (
            <li key={d.date} className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-3 text-sm">
              <span className="text-[#dbe4f7]" title={day(`${d.date}T12:00:00Z`)}>{weekday(d.date)}</span>
              <Bar value={d.avg ?? 0} max={100} tone={TONE[d.tone]} label={d.avg == null ? "No forecast" : `${d.avg}% cloud`} />
              <span className="w-40 text-right text-[#b0bed9]">{d.avg == null ? d.label : `${d.avg}% · ${d.label}`}</span>
            </li>
          ))}
        </ul>
        {best && <p className="mt-4 text-sm text-[#dbe4f7]">Best day for a clear picture: <strong>{weekday(best.date)} {best.date.slice(5)}</strong> ({best.avg}% cloud forecast).</p>}
        <p className="mt-3 text-xs text-[#7f8db0]">Sentinel-2 revisits a place about every 5 days, so a clear day does not always mean a new picture. Check Explore for new scenes.</p>
      </Panel>
    </div>
  );
}
