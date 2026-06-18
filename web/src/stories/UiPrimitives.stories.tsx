import type { Meta, StoryObj } from '@storybook/react-vite';
import { Search } from 'lucide-react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../components/ui/accordion';
import { Button } from '../components/ui/button';
import { Checkbox } from '../components/ui/checkbox';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from '../components/ui/command';
import { Input } from '../components/ui/input';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../components/ui/resizable';
import { ScrollArea } from '../components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
import { StoryFrame } from './StoryFrame';

const scrollItems = Array.from({ length: 12 }, (_, index) => ({
  id: `scroll-item-${index + 1}`,
  label: `Scrollable anonymized item ${index + 1}`,
}));

const meta = {
  title: 'Design System/UI Primitives',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const CoreControls: Story = {
  render: () => (
    <StoryFrame
      description="Radix and shadcn-style primitives with the app's VS Code-inspired styling."
      title="UI primitives"
    >
      <div className="storybookGrid">
        <section className="storybookSurface storybookStack">
          <div className="storybookRow">
            <Button>Default</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button size="icon">
              <Search size={14} />
            </Button>
          </div>
          <Input aria-label="Sample input" placeholder="Filter documents" />
          <div className="storybookRow">
            <Checkbox defaultChecked />
            <Checkbox checked="indeterminate" />
            <Checkbox />
          </div>
        </section>
        <section className="storybookSurface">
          <Accordion defaultValue={['a']} type="multiple">
            <AccordionItem value="a">
              <AccordionTrigger>Ingest summary</AccordionTrigger>
              <AccordionContent>Docling and MinerU completed with fused overlays.</AccordionContent>
            </AccordionItem>
            <AccordionItem value="b">
              <AccordionTrigger>Diagnostics</AccordionTrigger>
              <AccordionContent>One anonymized page Markdown step failed.</AccordionContent>
            </AccordionItem>
          </Accordion>
        </section>
        <section className="storybookSurface storybookViewportMedium">
          <ResizablePanelGroup direction="horizontal">
            <ResizablePanel defaultSize={35} minSize={20}>
              <div className="storybookDemoBox">Left pane</div>
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize={65} minSize={30}>
              <div className="storybookDemoBox">Main pane</div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </section>
      </div>
    </StoryFrame>
  ),
};

export const DataAndCommandPrimitives: Story = {
  render: () => (
    <StoryFrame
      description="Table, command palette, tooltip, and scroll primitives using anonymized labels."
      title="Data and overlay primitives"
    >
      <div className="storybookGrid">
        <section className="storybookSurface">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Step</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Read document</TableCell>
                <TableCell>ok</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Generate markdown</TableCell>
                <TableCell>error</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </section>
        <section className="storybookSurface">
          <Command>
            <CommandInput placeholder="Search commands" />
            <CommandList>
              <CommandEmpty>No command found.</CommandEmpty>
              <CommandGroup heading="Navigation">
                <CommandItem>
                  Open diagnostics<CommandShortcut>Enter</CommandShortcut>
                </CommandItem>
                <CommandItem>
                  Focus selected region<CommandShortcut>F</CommandShortcut>
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </section>
        <section className="storybookSurface storybookStack">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline">Hover for tooltip</Button>
              </TooltipTrigger>
              <TooltipContent>Tooltip content uses the shared primitive.</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <ScrollArea style={{ height: 140 }}>
            <div className="storybookStack">
              {scrollItems.map((item) => (
                <div key={item.id}>{item.label}</div>
              ))}
            </div>
          </ScrollArea>
        </section>
      </div>
    </StoryFrame>
  ),
};
