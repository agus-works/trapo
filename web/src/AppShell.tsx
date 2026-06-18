import { Link, Outlet } from '@tanstack/react-router';
import { Activity, Database, FileText, Moon, Search, Settings2, Sun } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { CommandCenter } from './CommandCenter';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './components/ui/tooltip';

type ThemeMode = 'light' | 'dark';

const themeStorageKey = 'trapo.theme';

export function AppShell() {
  const [theme, setTheme] = useState<ThemeMode>(() => readTheme());
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.title = 'Trapo';
    localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <TooltipProvider>
      <div className="rootShell">
        <aside className="activityBar" aria-label="Primary">
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="activityBrand" title="Trapo">
                <Database size={20} />
              </div>
            </TooltipTrigger>
            <TooltipContent side="right">Trapo</TooltipContent>
          </Tooltip>
          <nav className="activityNav">
            <ActivityLink ariaLabel="Documents" title="Documents" to="/">
              <FileText size={16} />
            </ActivityLink>
            <ActivityLink ariaLabel="Diagnostics" title="Diagnostics" to="/diagnostics">
              <Activity size={16} />
            </ActivityLink>
            <ActivityLink ariaLabel="Settings" title="Settings" to="/settings">
              <Settings2 size={16} />
            </ActivityLink>
          </nav>
          <div className="activityFooter">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  aria-label="Open command center"
                  onClick={() => setCommandOpen(true)}
                  type="button"
                >
                  <Search size={16} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">Command Center</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                  onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
                  type="button"
                >
                  {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {theme === 'dark' ? 'Light mode' : 'Dark mode'}
              </TooltipContent>
            </Tooltip>
          </div>
        </aside>
        <div className="workArea">
          <Outlet />
        </div>
      </div>
      <CommandCenter onOpenChange={setCommandOpen} open={commandOpen} />
    </TooltipProvider>
  );
}

function ActivityLink({
  ariaLabel,
  title,
  to,
  children,
}: {
  ariaLabel: string;
  title: string;
  to: '/' | '/diagnostics' | '/settings';
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          activeOptions={{ exact: to === '/' }}
          activeProps={{ className: 'active' }}
          aria-label={ariaLabel}
          title={title}
          to={to}
        >
          {children}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right">{title}</TooltipContent>
    </Tooltip>
  );
}

function readTheme(): ThemeMode {
  const stored = localStorage.getItem(themeStorageKey);
  if (stored === 'light' || stored === 'dark') {
    return stored;
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
