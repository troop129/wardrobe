'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  Shirt,
  Sparkles,
  Layers,
  LayoutGrid,
  History,
  BarChart3,
  Brain,
  Settings,
  Users,
  Bell,
  HeartHandshake,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: Home },
  { name: 'Wardrobe', href: '/dashboard/wardrobe', icon: Shirt },
  { name: 'Suggest Outfit', href: '/dashboard/suggest', icon: Sparkles },
  { name: 'Outfits', href: '/dashboard/outfits', icon: LayoutGrid },
  { name: 'Pairings', href: '/dashboard/pairings', icon: Layers },
  { name: 'History', href: '/dashboard/history', icon: History },
  { name: 'Family Feed', href: '/dashboard/family/feed', icon: HeartHandshake },
  { name: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
  { name: 'AI Learning', href: '/dashboard/learning', icon: Brain },
];

const secondaryNavigation = [
  { name: 'Family', href: '/dashboard/family', icon: Users },
  { name: 'Notifications', href: '/dashboard/notifications', icon: Bell },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
];

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
                {navigation.map((item) => {
                  // Dashboard only active on exact match, others match with prefix
                  const isActive = item.href === '/dashboard'
                    ? pathname === '/dashboard'
                    : pathname === item.href || pathname.startsWith(item.href + '/');
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
                {secondaryNavigation.map((item) => {
                  const matchesPath = pathname === item.href || pathname.startsWith(item.href + '/');
                  const claimedByPrimary = navigation.some(
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
