import { GripVertical } from 'lucide-react';
import type { KeyboardEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { readStringList, reorderIds } from '../helpers';
import type { WorkbenchTab } from '../types';
import styles from './WorkbenchTabs.module.css';

interface WorkbenchTabsProps {
  tabs: WorkbenchTab[];
  active: string;
  storageKey: string;
  onChange: (tabId: string) => void;
  ariaLabel?: string;
}

export function WorkbenchTabs({
  tabs,
  active,
  storageKey,
  onChange,
  ariaLabel = 'Workbench tabs',
}: WorkbenchTabsProps) {
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

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, tabId: string) {
    const currentIndex = orderedTabs.findIndex((tab) => tab.id === tabId);
    const nextIndex = nextKeyboardTabIndex(event.key, currentIndex, orderedTabs.length);
    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    const nextTab = orderedTabs[nextIndex];
    onChange(nextTab.id);
    const buttons =
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[nextIndex]?.focus();
  }

  return (
    <div aria-label={ariaLabel} className={styles.tabs} role="tablist">
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
          onKeyDown={(event) => handleKeyDown(event, tab.id)}
          role="tab"
          tabIndex={tab.id === active ? 0 : -1}
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

function nextKeyboardTabIndex(key: string, currentIndex: number, tabCount: number): number | null {
  if (currentIndex < 0 || tabCount === 0) {
    return null;
  }
  if (key === 'ArrowLeft') {
    return (currentIndex - 1 + tabCount) % tabCount;
  }
  if (key === 'ArrowRight') {
    return (currentIndex + 1) % tabCount;
  }
  if (key === 'Home') {
    return 0;
  }
  if (key === 'End') {
    return tabCount - 1;
  }
  return null;
}
