import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { DiagnosticsAnalyticsPanel } from '../diagnostics/DiagnosticsAnalyticsView';
import { DiagnosticsDetailsPane } from '../diagnostics/DiagnosticsDetailsPane';
import { DiagnosticsModelsPanel } from '../diagnostics/DiagnosticsModelsView';
import { DiagnosticsProgressPanel } from '../diagnostics/DiagnosticsProgressView';
import { DiagnosticsTimelinePanels } from '../diagnostics/DiagnosticsTimelinePanels';
import { DiagnosticsTimelineToolbar } from '../diagnostics/DiagnosticsTimelineToolbar';
import { buildRows, firstErrorId } from '../diagnostics/diagnosticsTimelineRows';
import { diagnosticEvents, diagnosticRuns, diagnosticTrace } from './fixtures/diagnosticFixtures';
import {
  diagnosticAnalytics,
  diagnosticModels,
  diagnosticProgress,
} from './fixtures/diagnosticProgressFixtures';
import { StoryFrame } from './StoryFrame';

const meta = {
  title: 'Features/Diagnostics',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const TimelineWaterfall: Story = {
  render: () => <DiagnosticsTimelineShowcase />,
};

export const PlannerProgress: Story = {
  render: () => <DiagnosticsProgressShowcase />,
};

export const PerformanceAnalytics: Story = {
  render: () => (
    <StoryFrame
      description="Synthetic diagnostics analytics across phases, engines, files, pages, and errors."
      title="Diagnostics performance analytics"
    >
      <section className="storybookSurface storybookViewportTall">
        <DiagnosticsAnalyticsPanel analytics={diagnosticAnalytics} />
      </section>
    </StoryFrame>
  ),
};

export const ModelLeases: Story = {
  render: () => (
    <StoryFrame
      description="Synthetic LM Studio lease order, context, and load-parameter reporting."
      title="Diagnostics models"
    >
      <section className="storybookSurface storybookViewportMedium">
        <DiagnosticsModelsPanel payload={diagnosticModels} />
      </section>
    </StoryFrame>
  ),
};

export const DetailsPane: Story = {
  render: () => {
    const span = diagnosticTrace.spans.find((item) => item.status === 'error') ?? null;
    return (
      <StoryFrame
        description="Failure details use anonymized stack traces and messages."
        title="Diagnostics details pane"
        width="narrow"
      >
        <section className="storybookSurface storybookViewportMedium">
          <DiagnosticsDetailsPane events={diagnosticEvents} span={span} />
        </section>
      </StoryFrame>
    );
  },
};

function DiagnosticsTimelineShowcase() {
  const rows = buildRows(diagnosticTrace.spans);
  const [selectedId, setSelectedId] = useState(firstErrorId(rows));
  const selectedSpan = rows.find((row) => row.span.span_id === selectedId)?.span ?? null;
  return (
    <StoryFrame
      description="Compact flamegraph/waterfall diagnostics view with synthetic timings and failures."
      title="Pipeline diagnostics"
    >
      <section className="storybookSurface storybookStack">
        <DiagnosticsTimelineToolbar
          effectiveRunId={diagnosticRuns[0].ingest_run_id}
          onQueryChange={() => undefined}
          onRunSelect={() => undefined}
          onStatusChange={() => undefined}
          query=""
          runs={diagnosticRuns}
          status="all"
          trace={diagnosticTrace}
        />
        <div className="storybookViewportTall">
          <DiagnosticsTimelinePanels
            events={diagnosticTrace.events}
            onSpanSelect={setSelectedId}
            rows={rows}
            selectedId={selectedId}
            selectedSpan={selectedSpan}
            summary={diagnosticTrace.summary}
          />
        </div>
      </section>
    </StoryFrame>
  );
}

function DiagnosticsProgressShowcase() {
  const [expandedIds, setExpandedIds] = useState(
    () => new Set(['file:anon-file-0001', 'page:anon-file-0001:document']),
  );
  return (
    <StoryFrame
      description="Planner progress uses anonymized work units and expandable task details."
      title="Diagnostics progress"
    >
      <section className="storybookSurface storybookViewportTall">
        <DiagnosticsProgressPanel
          expandedIds={expandedIds}
          onExpandedChange={setExpandedIds}
          progress={diagnosticProgress}
        />
      </section>
    </StoryFrame>
  );
}
