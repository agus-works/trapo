import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area';
import type { ComponentPropsWithoutRef } from 'react';

export function ScrollArea({
  className = '',
  children,
  ...props
}: ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>) {
  return (
    <ScrollAreaPrimitive.Root className={`scrollArea ${className}`} {...props}>
      <ScrollAreaPrimitive.Viewport className="scrollAreaViewport">
        {children}
      </ScrollAreaPrimitive.Viewport>
      <ScrollAreaPrimitive.Scrollbar className="scrollAreaScrollbar" orientation="vertical">
        <ScrollAreaPrimitive.Thumb className="scrollAreaThumb" />
      </ScrollAreaPrimitive.Scrollbar>
      <ScrollAreaPrimitive.Scrollbar
        className="scrollAreaScrollbar horizontal"
        orientation="horizontal"
      >
        <ScrollAreaPrimitive.Thumb className="scrollAreaThumb" />
      </ScrollAreaPrimitive.Scrollbar>
      <ScrollAreaPrimitive.Corner className="scrollAreaCorner" />
    </ScrollAreaPrimitive.Root>
  );
}
