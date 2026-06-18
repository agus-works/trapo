import type { ReactNode } from 'react';
import { cn } from '../../../lib/utils';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../../ui/accordion';
import { formatUnknown } from '../helpers';
import type { PropertySection, SelectionDetailsSection } from '../types';
import styles from './Inspector.module.css';

export function PropertyInspector({
  title,
  empty,
  sections,
}: {
  title?: string;
  empty: ReactNode;
  sections: PropertySection[];
}) {
  if (sections.length === 0) {
    return <div className={styles.emptyPropertyInspector}>{empty}</div>;
  }
  return (
    <div className={styles.propertyInspector}>
      {title && <h3>{title}</h3>}
      {sections.map((section) => (
        <section key={section.title}>
          <h4>{section.title}</h4>
          <dl>
            {section.rows.map((row) => (
              <PropertyRow key={row.label} label={row.label} value={row.value} />
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

export function SelectionDetails({
  title,
  empty,
  sections,
  defaultOpenIds,
}: {
  title?: ReactNode;
  empty: ReactNode;
  sections: SelectionDetailsSection[];
  defaultOpenIds?: string[];
}) {
  if (sections.length === 0) {
    return <div className={styles.emptyInspector}>{empty}</div>;
  }
  return (
    <Accordion
      className={styles.detailAccordion}
      defaultValue={defaultOpenIds ?? sections.slice(0, 3).map((section) => section.id)}
      type="multiple"
    >
      {title && (
        <div className={styles.detailInspectorTitle}>
          <h3>{title}</h3>
        </div>
      )}
      {sections.map((section) => (
        <AccordionItem key={section.id} value={section.id}>
          <AccordionTrigger>{section.title}</AccordionTrigger>
          <AccordionContent>{section.content}</AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}

export function KeyValueBlock({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined);
  if (entries.length === 0) {
    return <p className={styles.mutedText}>No metadata.</p>;
  }
  return (
    <dl className={cn(styles.keyValueBlock, styles.propertyGrid)}>
      {entries.slice(0, 40).map(([key, item]) => (
        <PropertyRow key={key} label={key} value={formatUnknown(item)} />
      ))}
    </dl>
  );
}

function PropertyRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
