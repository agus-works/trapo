import * as AccordionPrimitive from '@radix-ui/react-accordion';
import { ChevronRight } from 'lucide-react';
import type { ComponentPropsWithoutRef } from 'react';

export const Accordion = AccordionPrimitive.Root;

export function AccordionItem({
  className = '',
  ...props
}: ComponentPropsWithoutRef<typeof AccordionPrimitive.Item>) {
  return <AccordionPrimitive.Item className={`accordionItem ${className}`} {...props} />;
}

export function AccordionTrigger({
  children,
  className = '',
  ...props
}: ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="accordionHeader">
      <AccordionPrimitive.Trigger className={`accordionTrigger ${className}`} {...props}>
        <ChevronRight size={14} />
        <span>{children}</span>
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  );
}

export function AccordionContent({
  className = '',
  ...props
}: ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>) {
  return <AccordionPrimitive.Content className={`accordionContent ${className}`} {...props} />;
}
