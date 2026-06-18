import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { DiagnosticsDetailsPane } from '../diagnostics/DiagnosticsDetailsPane';
import { DiagnosticsTimelinePanels } from '../diagnostics/DiagnosticsTimelinePanels';
import { DiagnosticsTimelineToolbar } from '../diagnostics/DiagnosticsTimelineToolbar';
import { buildRows, firstErrorId } from '../diagnostics/diagnosticsTimelineRows';
import { diagnosticEvents, diagnosticRuns, diagnosticTrace } from './fixtures/diagnosticFixtures';
import { StoryFrame } from './StoryFrame';

const meta = {
  title: 'Features/Diagnostics',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const TimelineWaterfall: Story = {
  render: () => <DiagnosticsTimelineShowcase />,
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
