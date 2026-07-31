'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  PRIMARY_NAVIGATION,
  SECONDARY_NAVIGATION,
  isDashboardRouteActive,
} from '@/lib/navigation';

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-64 lg:flex-col">
      <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r bg-background px-5 pb-4">
        <div className="flex h-16 shrink-0 items-center">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <img src="/logo.svg" alt="Wardrowbe" className="h-6 w-6" />
            <span className="text-sm font-medium uppercase tracking-[0.15em]">wardrowbe</span>
          </Link>
        </div>
        <nav className="flex flex-1 flex-col">
          <ul role="list" className="flex flex-1 flex-col gap-y-7">
            <li>
              <ul role="list" className="space-y-0.5">
                {PRIMARY_NAVIGATION.map((item) => {
                  const isActive = isDashboardRouteActive(pathname, item.href);
                  return (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className={cn(
                          'group flex items-center gap-x-3 border-l-2 py-1.5 pl-3 text-sm leading-6 transition-colors',
                          isActive
                            ? 'border-foreground font-medium text-foreground'
                            : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                        )}
                      >
                        <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
            <li>
              <div className="text-[11px] font-medium uppercase tracking-[0.15em] text-muted-foreground/70">
                Settings
              </div>
              <ul role="list" className="mt-2 space-y-0.5">
                {SECONDARY_NAVIGATION.map((item) => {
                  const matchesPath = pathname === item.href || pathname.startsWith(item.href + '/');
                  const claimedByPrimary = PRIMARY_NAVIGATION.some(
                    (primary) => pathname === primary.href || pathname.startsWith(primary.href + '/')
                  );
                  const isActive = matchesPath && !claimedByPrimary;
                  return (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className={cn(
                          'group flex items-center gap-x-3 border-l-2 py-1.5 pl-3 text-sm leading-6 transition-colors',
                          isActive
                            ? 'border-foreground font-medium text-foreground'
                            : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                        )}
                      >
                        <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
          </ul>
        </nav>
      </div>
    </aside>
  );
}
