import type { ReactNode } from 'react';

export interface WorkbenchTab {
  id: string;
  label: string;
  icon?: ReactNode;
}

export interface PropertySection {
  title: string;
  rows: Array<{ label: string; value: ReactNode }>;
}

export interface SelectionDetailsSection {
  id: string;
  title: string;
  content: ReactNode;
}

export interface TreeNode {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
  checked?: boolean | 'indeterminate';
  hasChildren?: boolean;
  selected?: boolean;
  children?: TreeNode[];
  onExpand?: () => void;
  onSelect?: () => void;
  onCheckedChange?: (checked: boolean) => void;
}

export interface TreeGridNode extends Omit<TreeNode, 'children'> {
  badge?: ReactNode;
  children?: TreeGridNode[];
}
