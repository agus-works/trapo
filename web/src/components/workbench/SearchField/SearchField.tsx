import { Search } from 'lucide-react';
import { cn } from '../../../lib/utils';
import styles from './SearchField.module.css';

export function SearchField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <label className={cn(styles.searchField, className)}>
      <Search size={15} />
      <input
        aria-label={ariaLabel}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}
