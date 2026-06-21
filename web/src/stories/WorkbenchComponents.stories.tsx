import type { Meta, StoryObj } from '@storybook/react-vite';
import { Activity, FileText, FolderTree } from 'lucide-react';
import { useState } from 'react';
import {
  DenseDataTable,
  KeyValueBlock,
  PropertyInspector,
  SearchField,
  SelectionDetails,
  TreeGrid,
  TreeView,
  WorkbenchPane,
  WorkbenchStatusBar,
  WorkbenchTabs,
} from '../components/workbench';
import {
  tableColumns,
  tableRows,
  treeGridNodes,
  treeNodes,
  workbenchTabs,
} from './fixtures/anonymizedData';
import { StoryFrame } from './StoryFrame';

const meta = {
  title: 'Design System/Workbench Components',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const NavigationAndTabs: Story = {
  render: () => <WorkbenchNavigationShowcase />,
};

export const DataAndInspector: Story = {
  render: () => <WorkbenchDataShowcase />,
};

function WorkbenchNavigationShowcase() {
  const [expandedIds, setExpandedIds] = useState(new Set(['folder:sample', 'file:1', 'overlays']));
  const [activeTab, setActiveTab] = useState('preview');
  const toggle = (id: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };
  return (
    <StoryFrame
      description="Explorer and tab primitives used across the document workbench."
      title="Workbench navigation"
    >
      <div className="storybookGrid">
        <WorkbenchPane icon={<FolderTree size={15} />} title="Explorer">
          <SearchField
            ariaLabel="Search sample tree"
            onChange={() => undefined}
            placeholder="Filter sample corpus"
            value=""
          />
          <TreeView expandedIds={expandedIds} nodes={treeNodes} onToggle={toggle} />
        </WorkbenchPane>
        <WorkbenchPane icon={<Activity size={15} />} title="Overlay engines">
          <TreeGrid expandedIds={expandedIds} nodes={treeGridNodes} onToggle={toggle} />
        </WorkbenchPane>
        <section className="storybookSurface storybookStack">
          <WorkbenchTabs
            active={activeTab}
            ariaLabel="Workbench sample tabs"
            onChange={setActiveTab}
            storageKey="storybook-tabs"
            tabs={workbenchTabs}
          />
          <WorkbenchStatusBar
            items={[
              { label: 'documents', value: 2 },
              { label: 'regions', value: 397 },
              { label: 'failures', value: 1 },
            ]}
          />
        </section>
      </div>
    </StoryFrame>
  );
}

function WorkbenchDataShowcase() {
  const [filter, setFilter] = useState('');
  return (
    <StoryFrame
      description="Dense table and inspector components with fake pipeline metadata."
      title="Workbench data surfaces"
    >
      <div className="storybookGrid">
        <section className="storybookSurface storybookViewportMedium">
          <DenseDataTable
            columns={tableColumns}
            data={tableRows}
            getRowId={(row) => row.id}
            globalFilter={filter}
            onGlobalFilterChange={setFilter}
            selectedId="r3"
          />
        </section>
        <section className="storybookSurface storybookStack">
          <PropertyInspector
            empty="No selection."
            sections={[
              {
                rows: [
                  { label: 'File', value: 'sample-research-brief.pdf' },
                  { label: 'Status', value: 'completed_with_errors' },
                ],
                title: 'Selection',
              },
            ]}
            title="Properties"
          />
          <SelectionDetails
            empty="No region selected."
            sections={[
              {
                content: <KeyValueBlock value={{ engine: 'infinity', page: 2, status: 'ok' }} />,
                id: 'metadata',
                title: 'Metadata',
              },
            ]}
            title={
              <span>
                <FileText size={14} /> Region details
              </span>
            }
          />
        </section>
      </div>
    </StoryFrame>
  );
}
