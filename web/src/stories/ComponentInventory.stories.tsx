import type { Meta, StoryObj } from '@storybook/react-vite';
import { StoryFrame } from './StoryFrame';

const inventory = [
  {
    components: [
      'Button',
      'Input',
      'Checkbox',
      'Accordion',
      'Table',
      'Command',
      'Tooltip',
      'ScrollArea',
      'ResizablePanelGroup',
    ],
    title: 'UI primitives',
  },
  {
    components: [
      'WorkbenchPane',
      'PaneHeader',
      'TreeView',
      'TreeGrid',
      'DenseDataTable',
      'SearchField',
      'WorkbenchStatusBar',
      'WorkbenchTabs',
      'PropertyInspector',
      'SelectionDetails',
      'KeyValueBlock',
    ],
    title: 'Workbench shared components',
  },
  {
    components: [
      'DocumentTopBar',
      'PdfPreviewToolbar',
      'OverlayDetailsPane',
      'ExplorerDetailsPane',
      'FolderContentView',
      'PreviewPane',
      'MarkdownDocumentView',
      'PdfDocumentPreview',
      'OverlayLayer',
    ],
    title: 'Document feature surfaces',
  },
  {
    components: [
      'DiagnosticsTimelineView',
      'DiagnosticsTimelineToolbar',
      'DiagnosticsTimelinePanels',
      'DiagnosticsDetailsPane',
      'DiagnosticsPage',
    ],
    title: 'Diagnostics feature surfaces',
  },
  {
    components: ['AppShell', 'CommandCenter', 'SettingsPage', 'DocumentsPage'],
    title: 'Route and shell containers',
  },
];

const meta = {
  title: 'Design System/Component Inventory',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Catalog: Story = {
  render: () => (
    <StoryFrame
      description="A living index of the current React component surface. Stories use anonymized fixtures and should be updated whenever components or feature surfaces change."
      title="Trapo component inventory"
    >
      <div className="storybookInventory">
        {inventory.map((group) => (
          <section key={group.title}>
            <h2>{group.title}</h2>
            <ul>
              {group.components.map((component) => (
                <li key={component}>{component}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </StoryFrame>
  ),
};
