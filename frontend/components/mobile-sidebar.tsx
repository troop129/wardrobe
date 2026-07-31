'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  PRIMARY_NAVIGATION,
  SECONDARY_NAVIGATION,
  isDashboardRouteActive,
} from '@/lib/navigation';

interface MobileSidebarProps {
  open: boolean;
  onClose: () => void;
}

export function MobileSidebar({ open, onClose }: MobileSidebarProps) {
  const pathname = usePathname();

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  return (
    <div className={cn('lg:hidden', !open && 'pointer-events-none')}>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-50 bg-black/50 transition-opacity duration-300',
          open ? 'opacity-100' : 'opacity-0'
        )}
        onClick={onClose}
      />

      {/* Sidebar panel */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-72 bg-card transition-transform duration-300 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Close button */}
        <button
          type="button"
          className="absolute right-4 top-4 p-2 text-muted-foreground hover:text-foreground"
          onClick={onClose}
        >
          <span className="sr-only">Close sidebar</span>
          <X className="h-6 w-6" />
        </button>

        <div className="flex h-full flex-col gap-y-5 overflow-y-auto px-6 pb-4">
          <div className="flex h-16 shrink-0 items-center">
            <Link href="/dashboard" className="flex items-center gap-3" onClick={onClose}>
              <img src="/logo.svg" alt="Wardrowbe" className="h-7 w-7" />
              <span className="text-lg font-semibold tracking-tight">wardrowbe</span>
            </Link>
          </div>
          <nav className="flex flex-1 flex-col">
            <ul role="list" className="flex flex-1 flex-col gap-y-7">
              <li>
                <ul role="list" className="-mx-2 space-y-1">
                  {PRIMARY_NAVIGATION.map((item) => {
                    const isActive = isDashboardRouteActive(pathname, item.href);
                    return (
                      <li key={item.name}>
                        <Link
                          href={item.href}
                          onClick={onClose}
                          className={cn(
                            'group flex gap-x-3 rounded-md border-l-2 border-transparent py-2 pl-3 pr-2 text-sm font-medium leading-6',
                            isActive
                              ? 'border-foreground bg-muted/70 text-foreground'
                              : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
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
                <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                  Settings
                </div>
                <ul role="list" className="-mx-2 mt-2 space-y-1">
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
                          onClick={onClose}
                          className={cn(
                            'group flex gap-x-3 rounded-md border-l-2 border-transparent py-2 pl-3 pr-2 text-sm font-medium leading-6',
                            isActive
                              ? 'border-foreground bg-muted/70 text-foreground'
                              : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
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
      </div>
    </div>
  );
}
