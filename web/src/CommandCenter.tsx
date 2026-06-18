import { useNavigate } from '@tanstack/react-router';
import { FileSearch, Search, TerminalSquare } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from './components/ui/command';
import type {
  CommandSearchResultRecord,
  GlobalSearchResultRecord,
  SearchHighlightRecord,
} from './generated/model';
import { useCommandSearchQuery, useGlobalSearchQuery } from './queries/hooks';

interface CommandCenterProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandCenter({ open, onOpenChange }: CommandCenterProps) {
  const navigate = useNavigate();
  const [rawQuery, setRawQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const commandMode = rawQuery.startsWith('>');
  const activeQuery = commandMode ? rawQuery.replace(/^>\s*/, '') : rawQuery;
  const commandQuery = useCommandSearchQuery({ limit: commandMode ? 30 : 12, q: debouncedQuery });
  const globalQuery = useGlobalSearchQuery({
    limit: 12,
    q: commandMode ? null : debouncedQuery,
  });
  const commandResults = commandQuery.data ?? [];
  const globalResults = globalQuery.data ?? [];

  useEffect(() => {
    if (!open) {
      return;
    }
    const timer = window.setTimeout(() => setDebouncedQuery(activeQuery.trim()), 120);
    return () => window.clearTimeout(timer);
  }, [activeQuery, open]);

  useEffect(() => {
    if (open) {
      setRawQuery('');
      setDebouncedQuery('');
      setNotice(null);
    }
  }, [open]);

  const groupedCommands = useMemo(() => groupCommands(commandResults), [commandResults]);

  async function navigateTo(route: unknown, search: unknown = undefined) {
    const appRoute = appRouteValue(route);
    if (!appRoute) {
      setNotice('No route is available for this result.');
      return;
    }
    await navigate({
      search: searchRecord(search) as never,
      to: appRoute as never,
    });
    onOpenChange(false);
  }

  async function executeCommand(command: CommandSearchResultRecord) {
    setNotice(null);
    if (command.action.type === 'navigate') {
      await navigateTo(command.action.route, command.action.search);
      return;
    }
    setNotice(`Unsupported command action: ${command.action.type}`);
  }

  async function executeGlobalResult(result: GlobalSearchResultRecord) {
    const route = result.route as { to?: unknown; search?: unknown } | undefined;
    await navigateTo(route?.to, route?.search);
  }

  if (!open) {
    return null;
  }

  return (
    <div className="commandOverlay">
      <button
        aria-label="Close command center"
        className="commandBackdrop"
        onClick={() => onOpenChange(false)}
        type="button"
      />
      <div aria-modal="true" className="commandDialog" role="dialog">
        <Command shouldFilter={false}>
          <div className="commandInputRow">
            {commandMode ? <TerminalSquare size={15} /> : <Search size={15} />}
            <CommandInput
              autoFocus
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  onOpenChange(false);
                }
              }}
              onValueChange={setRawQuery}
              placeholder={commandMode ? 'Run command' : 'Search documents or run > command'}
              value={rawQuery}
            />
          </div>
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>
            {groupedCommands.map(([group, commands]) => (
              <CommandGroup heading={group} key={group}>
                {commands.map((command) => (
                  <CommandItem
                    key={command.command_id}
                    onSelect={() => void executeCommand(command)}
                    value={`command-${command.command_id}`}
                  >
                    <Search size={14} />
                    <div className="commandResultText">
                      <strong>
                        <HighlightedText
                          field="label"
                          highlights={command.highlights ?? []}
                          text={command.label}
                        />
                      </strong>
                      <span>{command.description}</span>
                    </div>
                    {command.shortcut && <CommandShortcut>{command.shortcut}</CommandShortcut>}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            {!commandMode && globalResults.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Search Results">
                  {globalResults.map((result) => (
                    <CommandItem
                      key={result.result_id}
                      onSelect={() => void executeGlobalResult(result)}
                      value={`global-${result.result_id}`}
                    >
                      <FileSearch size={14} />
                      <div className="commandResultText">
                        <strong>
                          <HighlightedText
                            field="label"
                            highlights={result.highlights ?? []}
                            text={result.label}
                          />
                        </strong>
                        <span>
                          <HighlightedText
                            field="snippet"
                            highlights={result.highlights ?? []}
                            text={result.snippet}
                          />
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
        {notice && <div className="commandNotice">{notice}</div>}
      </div>
    </div>
  );
}

function groupCommands(
  commands: CommandSearchResultRecord[],
): Array<[string, CommandSearchResultRecord[]]> {
  const groups = new Map<string, CommandSearchResultRecord[]>();
  for (const command of commands) {
    const existing = groups.get(command.group) ?? [];
    existing.push(command);
    groups.set(command.group, existing);
  }
  return Array.from(groups.entries());
}

function appRouteValue(route: unknown): string | null {
  return route === '/' ? '/' : null;
}

function searchRecord(search: unknown): Record<string, unknown> {
  return search && typeof search === 'object' ? (search as Record<string, unknown>) : {};
}

function HighlightedText({
  text,
  highlights,
  field,
}: {
  text: string;
  highlights: SearchHighlightRecord[];
  field: string;
}) {
  const spans = highlights
    .filter((highlight) => highlight.field === field)
    .sort((a, b) => a.start - b.start);
  if (spans.length === 0) {
    return <>{text}</>;
  }
  const parts: Array<{ text: string; highlighted: boolean }> = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start > cursor) {
      parts.push({ highlighted: false, text: text.slice(cursor, span.start) });
    }
    parts.push({ highlighted: true, text: text.slice(span.start, span.end) });
    cursor = Math.max(cursor, span.end);
  }
  if (cursor < text.length) {
    parts.push({ highlighted: false, text: text.slice(cursor) });
  }
  return (
    <>
      {parts.map((part, index) =>
        part.highlighted ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: parts are derived from stable text spans
          <mark key={index}>{part.text}</mark>
        ) : (
          // biome-ignore lint/suspicious/noArrayIndexKey: parts are derived from stable text spans
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}
