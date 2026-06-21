import { useDiagnosticAnalyticsQuery } from '../queries/hooks';
import styles from './DiagnosticsAnalyticsView.module.css';
import { formatDuration, formatPercent } from './diagnosticsFormat';
import type {
  DiagnosticAnalyticsPayload,
  DiagnosticBreakdownRecord,
  DiagnosticSlowSpanRecord,
  DiagnosticWorkUnitRecord,
} from './types';

export function DiagnosticsAnalyticsView({ runId }: { runId: number | null }) {
  const analyticsQuery = useDiagnosticAnalyticsQuery(runId);
  const analytics = analyticsQuery.data;
  if (!analytics) {
    return <div className={styles.empty}>Loading performance analytics...</div>;
  }
  return <DiagnosticsAnalyticsPanel analytics={analytics} />;
}

export function DiagnosticsAnalyticsPanel({
  analytics,
}: {
  analytics: DiagnosticAnalyticsPayload;
}) {
  return (
    <section className={styles.analyticsShell}>
      <div className={styles.scroll}>
        <SummaryGrid analytics={analytics} />
        <RecommendationList analytics={analytics} />
        <div className={styles.reportGrid}>
          <BreakdownReport rows={analytics.phase_breakdown} title="Phase Share" />
          <BreakdownReport rows={analytics.engine_breakdown} title="Engine Share" />
          <BreakdownReport rows={analytics.model_breakdown} title="Model Share" />
          <BreakdownReport rows={analytics.error_breakdown} title="Error Cost" />
          <BreakdownReport rows={analytics.file_breakdown} title="Slowest Files" />
          <BreakdownReport rows={analytics.page_breakdown} title="Slowest Pages" />
        </div>
        <SlowWorkUnits units={analytics.slow_work_units} />
        <SlowSpans spans={analytics.slow_spans} />
      </div>
    </section>
  );
}

function SummaryGrid({ analytics }: { analytics: DiagnosticAnalyticsPayload }) {
  const failedShare = analytics.summary.duration_ms
    ? (analytics.summary.failed_llm_duration_ms / analytics.summary.duration_ms) * 100
    : 0;
  return (
    <div className={styles.summaryGrid}>
      <Metric label="Run duration" value={formatDuration(analytics.summary.duration_ms)} />
      <Metric label="Work units" value={analytics.summary.work_unit_count.toLocaleString()} />
      <Metric label="Failed units" value={analytics.summary.failed_work_unit_count} />
      <Metric label="Spans" value={analytics.summary.span_count.toLocaleString()} />
      <Metric label="Model leases" value={analytics.summary.model_lease_count} />
      <Metric label="Failed LLM cost" value={formatPercent(failedShare)} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className={styles.metric}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RecommendationList({ analytics }: { analytics: DiagnosticAnalyticsPayload }) {
  return (
    <div className={styles.recommendations}>
      {analytics.recommendations.map((item) => (
        <div className={styles.recommendation} data-severity={item.severity} key={item.id}>
          <strong>{item.title}</strong>
          <span>{item.detail}</span>
        </div>
      ))}
    </div>
  );
}

function BreakdownReport({ rows, title }: { rows: DiagnosticBreakdownRecord[]; title: string }) {
  const maxDuration = Math.max(...rows.map((row) => row.duration_ms), 1);
  return (
    <section className={styles.report}>
      <header>
        <strong>{title}</strong>
        <span>{rows.length} rows</span>
      </header>
      <div className={styles.barRows}>
        {rows.slice(0, 10).map((row) => (
          <div className={styles.barRow} key={row.id} title={row.label}>
            <span>{row.label}</span>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{ width: `${Math.max(2, (row.duration_ms / maxDuration) * 100)}%` }}
              />
            </div>
            <span>{formatDuration(row.duration_ms)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SlowWorkUnits({ units }: { units: DiagnosticWorkUnitRecord[] }) {
  return (
    <section className={styles.tableSection}>
      <header>Slowest Work Units</header>
      <table className={styles.denseTable}>
        <thead>
          <tr>
            <th>Task</th>
            <th>Status</th>
            <th>Engine</th>
            <th>Model</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {units.slice(0, 20).map((unit) => (
            <tr key={unit.work_unit_id}>
              <td>{unit.work_key}</td>
              <td>{unit.status}</td>
              <td>{unit.engine}</td>
              <td>{unit.model}</td>
              <td>{formatDuration(unit.duration_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function SlowSpans({ spans }: { spans: DiagnosticSlowSpanRecord[] }) {
  return (
    <section className={styles.tableSection}>
      <header>Slowest Spans</header>
      <table className={styles.denseTable}>
        <thead>
          <tr>
            <th>Span</th>
            <th>Status</th>
            <th>Step</th>
            <th>Engine</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {spans.slice(0, 20).map((span) => (
            <tr key={span.span_id}>
              <td>{span.span_id}</td>
              <td>{span.status}</td>
              <td>{span.pipeline_step}</td>
              <td>{span.annotation_engine ?? span.category}</td>
              <td>{formatDuration(span.duration_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
