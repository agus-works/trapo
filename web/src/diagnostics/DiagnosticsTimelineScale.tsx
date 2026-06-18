import styles from './DiagnosticsTimelineView.module.css';
import type { TimelineTick } from './diagnosticsTimelineRows';

export function DiagnosticsTimelineAxis({ ticks }: { ticks: TimelineTick[] }) {
  return (
    <div className={styles.axisRow}>
      <span>Step</span>
      <div className={styles.axisTrack}>
        {ticks.map((tick) => (
          <span
            className={styles.axisTick}
            data-edge={tick.edge}
            key={`${tick.elapsedMs}-${tick.leftPct}`}
            style={{ left: `${tick.leftPct}%` }}
          >
            {tick.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DiagnosticsTimelineGrid({ ticks }: { ticks: TimelineTick[] }) {
  return (
    <div aria-hidden className={styles.gridLayer}>
      {ticks.map((tick) => (
        <span
          className={styles.gridLine}
          key={`${tick.elapsedMs}-${tick.leftPct}`}
          style={{ left: `${tick.leftPct}%` }}
        />
      ))}
    </div>
  );
}
