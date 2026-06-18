import { Command as CommandPrimitive } from 'cmdk';
import type { ComponentPropsWithoutRef } from 'react';
import { cn } from '../../lib/utils';

export function Command({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive>) {
  return <CommandPrimitive className={cn('commandRoot', className)} {...props} />;
}

export function CommandInput({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.Input>) {
  return <CommandPrimitive.Input className={cn('commandInput', className)} {...props} />;
}

export function CommandList({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.List>) {
  return <CommandPrimitive.List className={cn('commandList', className)} {...props} />;
}

export function CommandEmpty({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.Empty>) {
  return <CommandPrimitive.Empty className={cn('commandEmpty', className)} {...props} />;
}

export function CommandGroup({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.Group>) {
  return <CommandPrimitive.Group className={cn('commandGroup', className)} {...props} />;
}

export function CommandItem({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.Item>) {
  return <CommandPrimitive.Item className={cn('commandItem', className)} {...props} />;
}

export function CommandSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof CommandPrimitive.Separator>) {
  return <CommandPrimitive.Separator className={cn('commandSeparator', className)} {...props} />;
}

export function CommandShortcut({ className, ...props }: ComponentPropsWithoutRef<'span'>) {
  return <span className={cn('commandShortcut', className)} {...props} />;
}
