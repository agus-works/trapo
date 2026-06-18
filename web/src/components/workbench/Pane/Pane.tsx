import type { ReactNode } from 'react';
import { cn } from '../../../lib/utils';
import styles from './Pane.module.css';

export function WorkbenchPane({
  title,
  icon,
  actions,
  children,
  className,
}: {
  title: string;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn(styles.pane, className)}>
      <PaneHeader actions={actions} icon={icon} title={title} />
      {children}
    </section>
  );
}

export function PaneHeader({
  title,
  icon,
  actions,
}: {
  title: string;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className={styles.paneHeader}>
      <div>
        {icon}
        <span>{title}</span>
      </div>
      {actions && <div className={styles.paneHeaderActions}>{actions}</div>}
    </div>
  );
}
