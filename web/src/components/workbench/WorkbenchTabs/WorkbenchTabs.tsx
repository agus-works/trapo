import { GripVertical } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { readStringList, reorderIds } from '../helpers';
import type { WorkbenchTab } from '../types';
import styles from './WorkbenchTabs.module.css';

export function WorkbenchTabs({
  tabs,
  active,
  storageKey,
  onChange,
}: {
  tabs: WorkbenchTab[];
  active: string;
  storageKey: string;
  onChange: (tabId: string) => void;
}) {
  const [orderedIds, setOrderedIds] = useState<string[]>(() => readStringList(storageKey));
  const orderedTabs = useMemo(() => {
    const byId = new Map(tabs.map((tab) => [tab.id, tab]));
    const ordered = orderedIds
      .map((id) => byId.get(id))
      .filter((tab): tab is WorkbenchTab => tab !== undefined);
    const missing = tabs.filter((tab) => !orderedIds.includes(tab.id));
    return [...ordered, ...missing];
  }, [orderedIds, tabs]);

  useEffect(() => {
    if (orderedIds.length > 0) {
      localStorage.setItem(storageKey, JSON.stringify(orderedIds));
    }
  }, [orderedIds, storageKey]);

  return (
    <div className={styles.tabs} role="tablist">
      {orderedTabs.map((tab) => (
        <button
          aria-selected={tab.id === active}
          className={tab.id === active ? styles.active : undefined}
          draggable
          key={tab.id}
          onClick={() => onChange(tab.id)}
          onDragOver={(event) => event.preventDefault()}
          onDragStart={(event) => event.dataTransfer.setData('text/plain', tab.id)}
          onDrop={(event) => {
            event.preventDefault();
            const draggedId = event.dataTransfer.getData('text/plain');
            if (draggedId && draggedId !== tab.id) {
              setOrderedIds(
                reorderIds(
                  orderedTabs.map((item) => item.id),
                  draggedId,
                  tab.id,
                ),
              );
            }
          }}
          role="tab"
          type="button"
        >
          <GripVertical size={12} />
          {tab.icon}
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  );
}
