export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

export function compactText(value: string, maxLength: number): string {
  const text = value.replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 3))}...`;
}

export function shortHash(value: string | null | undefined, length = 12): string {
  if (!value) {
    return 'none';
  }
  return value.length > length ? value.slice(0, length) : value;
}

export function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
