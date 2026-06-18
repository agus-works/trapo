export function reorderIds(ids: string[], draggedId: string, targetId: string): string[] {
  const next = ids.filter((id) => id !== draggedId);
  const targetIndex = next.indexOf(targetId);
  if (targetIndex === -1) {
    return ids;
  }
  next.splice(targetIndex, 0, draggedId);
  return next;
}

export function readStringList(storageKey: string): string[] {
  try {
    const raw = localStorage.getItem(storageKey);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) && parsed.every((item) => typeof item === 'string') ? parsed : [];
  } catch {
    return [];
  }
}

export function formatUnknown(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length <= 6
      ? value.map(String).join(', ')
      : `${value.slice(0, 6).map(String).join(', ')} +${value.length - 6}`;
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value);
  }
  return String(value);
}

export function sortingIndicator(value: false | 'asc' | 'desc'): string {
  if (value === 'asc') {
    return ' ↑';
  }
  if (value === 'desc') {
    return ' ↓';
  }
  return '';
}
