import type { ComponentPropsWithoutRef } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';

export type { ImperativePanelHandle };
export { Panel as ResizablePanel, PanelGroup as ResizablePanelGroup };

export function ResizableHandle({
  className = '',
  orientation = 'vertical',
  ...props
}: ComponentPropsWithoutRef<typeof PanelResizeHandle> & {
  orientation?: 'horizontal' | 'vertical';
}) {
  return <PanelResizeHandle className={`resizeHandle ${orientation} ${className}`} {...props} />;
}
