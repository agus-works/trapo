import type { ReactNode } from 'react';
import styles from './StatusBar.module.css';

export function WorkbenchStatusBar({
  items,
}: {
  items: Array<{ label: string; value: ReactNode }>;
}) {
  return (
    <footer className={styles.statusBar}>
      {items.map((item) => (
        <span key={item.label}>
          <strong>{item.value}</strong> {item.label}
        </span>
      ))}
    </footer>
  );
}
