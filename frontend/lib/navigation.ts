import {
  BarChart3,
  History,
  Home,
  LayoutGrid,
  Settings,
  Shirt,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

export interface DashboardNavigationItem {
  name: string;
  href: string;
  icon: LucideIcon;
}

export const PRIMARY_NAVIGATION: DashboardNavigationItem[] = [
  { name: 'Home', href: '/dashboard', icon: Home },
  { name: 'Wardrobe', href: '/dashboard/wardrobe', icon: Shirt },
  { name: 'Outfit', href: '/dashboard/suggest', icon: Sparkles },
  { name: 'Outfits', href: '/dashboard/outfits', icon: LayoutGrid },
  { name: 'History', href: '/dashboard/history', icon: History },
];

export const SECONDARY_NAVIGATION: DashboardNavigationItem[] = [
  { name: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
];

export const MOBILE_NAVIGATION: DashboardNavigationItem[] = [
  ...PRIMARY_NAVIGATION.slice(0, 4),
  SECONDARY_NAVIGATION[1],
];

const EXTRA_ROUTE_TITLES: Array<{ href: string; name: string }> = [
  { href: '/dashboard/notifications', name: 'Notifications' },
  { href: '/dashboard/learning', name: 'AI Learning' },
  { href: '/dashboard/pairings', name: 'Pairings' },
  { href: '/dashboard/family/feed', name: 'Family Feed' },
  { href: '/dashboard/family', name: 'Family' },
];

export function isDashboardRouteActive(pathname: string, href: string): boolean {
  return href === '/dashboard'
    ? pathname === href
    : pathname === href || pathname.startsWith(`${href}/`);
}

export function getDashboardRouteTitle(pathname: string): string {
  const routes = [...EXTRA_ROUTE_TITLES, ...PRIMARY_NAVIGATION, ...SECONDARY_NAVIGATION]
    .sort((a, b) => b.href.length - a.href.length);
  return routes.find((item) => isDashboardRouteActive(pathname, item.href))?.name ?? 'Wardrowbe';
}
