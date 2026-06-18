import { ChevronDown, ChevronRight } from 'lucide-react';
import type { CSSProperties } from 'react';
import { cn } from '../../../lib/utils';
import { Checkbox } from '../../ui/checkbox';
import type { TreeGridNode, TreeNode } from '../types';
import styles from './Tree.module.css';

export function TreeView({
  nodes,
  expandedIds,
  onToggle,
  className,
}: {
  nodes: TreeNode[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cn(styles.treeView, className)}>
      {nodes.map((node) => (
        <TreeViewRow
          expandedIds={expandedIds}
          key={node.id}
          level={0}
          node={node}
          onToggle={onToggle}
        />
      ))}
    </div>
  );
}

export function TreeGrid({
  nodes,
  expandedIds,
  onToggle,
  className,
}: {
  nodes: TreeGridNode[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cn(styles.treeGrid, className)}>
      {nodes.map((node) => (
        <TreeGridRow
          expandedIds={expandedIds}
          key={node.id}
          level={0}
          node={node}
          onToggle={onToggle}
        />
      ))}
    </div>
  );
}

function TreeViewRow({
  node,
  level,
  expandedIds,
  onToggle,
}: {
  node: TreeNode;
  level: number;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const childCount = node.children?.length ?? 0;
  const hasChildren = node.hasChildren ?? childCount > 0;
  const expanded = expandedIds.has(node.id);
  const onRowToggle = () => {
    if (!expanded && childCount === 0) {
      node.onExpand?.();
    }
    onToggle(node.id);
  };
  return (
    <>
      <div
        className={cn(
          styles.treeRow,
          node.checked !== undefined && styles.treeRowWithCheckbox,
          node.selected && styles.active,
        )}
        id={node.id}
        style={treeLevelStyle(level)}
      >
        <TreeTwisty
          expanded={expanded}
          hasChildren={hasChildren}
          label={node.label}
          onToggle={onRowToggle}
        />
        {node.checked !== undefined && (
          <Checkbox
            checked={node.checked}
            onCheckedChange={(value) => node.onCheckedChange?.(value === true)}
          />
        )}
        <TreeLabelButton icon={node.icon} label={node.label} onSelect={node.onSelect} />
        {node.badge && <small>{node.badge}</small>}
      </div>
      {hasChildren && expanded && (
        <div>
          {node.children?.map((child) => (
            <TreeViewRow
              expandedIds={expandedIds}
              key={child.id}
              level={level + 1}
              node={child}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </>
  );
}

function TreeGridRow({
  node,
  level,
  expandedIds,
  onToggle,
}: {
  node: TreeGridNode;
  level: number;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const childCount = node.children?.length ?? 0;
  const hasChildren = node.hasChildren ?? childCount > 0;
  const expanded = expandedIds.has(node.id);
  const onRowToggle = () => {
    if (!expanded && childCount === 0) {
      node.onExpand?.();
    }
    onToggle(node.id);
  };
  return (
    <>
      <div
        className={cn(styles.treeGridRow, node.selected && styles.active)}
        id={node.id}
        style={treeLevelStyle(level)}
      >
        <div className={styles.treeGridName}>
          <TreeTwisty
            expanded={expanded}
            hasChildren={hasChildren}
            label={node.label}
            onToggle={onRowToggle}
          />
          <TreeLabelButton icon={node.icon} label={node.label} onSelect={node.onSelect} />
        </div>
        <span className={styles.treeGridBadge}>{node.badge}</span>
        <span className={styles.treeGridSwitchCell}>
          {node.checked !== undefined && (
            <button
              aria-checked={node.checked === 'indeterminate' ? 'mixed' : node.checked}
              className={styles.treeGridSwitch}
              onClick={() => node.onCheckedChange?.(node.checked !== true)}
              role="switch"
              type="button"
            >
              <span />
            </button>
          )}
        </span>
      </div>
      {hasChildren && expanded && (
        <div>
          {node.children?.map((child) => (
            <TreeGridRow
              expandedIds={expandedIds}
              key={child.id}
              level={level + 1}
              node={child}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </>
  );
}

function TreeTwisty({
  expanded,
  hasChildren,
  label,
  onToggle,
}: {
  expanded: boolean;
  hasChildren: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
      className={styles.treeTwisty}
      disabled={!hasChildren}
      onClick={onToggle}
      type="button"
    >
      {hasChildren ? expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} /> : null}
    </button>
  );
}

function TreeLabelButton({ icon, label, onSelect }: Pick<TreeNode, 'icon' | 'label' | 'onSelect'>) {
  return (
    <button className={styles.treeLabelButton} onClick={onSelect} type="button">
      {icon}
      <span>{label}</span>
    </button>
  );
}

function treeLevelStyle(level: number): CSSProperties {
  return { '--tree-level': String(level) } as CSSProperties;
}
