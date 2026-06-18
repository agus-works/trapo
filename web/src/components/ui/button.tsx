import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export function Button({
  className,
  variant = 'default',
  size = 'default',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'ghost' | 'outline';
  size?: 'default' | 'sm' | 'icon';
}) {
  return (
    <button
      className={cn('uiButton', `uiButton-${variant}`, `uiButton-${size}`, className)}
      type="button"
      {...props}
    />
  );
}
