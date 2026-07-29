'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { Check, LayoutGrid, List, Loader2, Search } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { useItems } from '@/lib/hooks/use-items';
import { cn } from '@/lib/utils';
import { CLOTHING_TYPES, type Item } from '@/lib/types';

const PAGE_SIZE = 60;

// Rough outfit-building order (top -> layer -> bottom -> shoes -> extras) so
// grouped sections read in the same order you'd actually assemble a look,
// rather than alphabetically. Mirrors the role grouping the backend uses for
// outfit assembly (see backend/app/utils/clothing.py::ITEM_ROLE), but grouped
// by exact clothing type (not role) since that's the more useful unit for
// browsing a wardrobe to build an outfit by hand.
const TYPE_GROUP_ORDER: Record<string, number> = {
  shirt: 0,
  't-shirt': 0,
  top: 0,
  blouse: 0,
  polo: 0,
  'tank-top': 0,
  sweater: 1,
  cardigan: 1,
  vest: 1,
  jacket: 2,
  coat: 2,
  hoodie: 2,
  blazer: 2,
  dress: 3,
  jumpsuit: 3,
  suit: 3,
  pants: 4,
  jeans: 4,
  shorts: 4,
  skirt: 4,
  shoes: 5,
  sneakers: 5,
  boots: 5,
  sandals: 5,
  socks: 6,
  tie: 6,
  hat: 6,
  scarf: 6,
  belt: 6,
  bag: 6,
  accessories: 6,
  cologne: 6,
};

const TYPE_LABELS: Record<string, string> = Object.fromEntries(
  CLOTHING_TYPES.map((t) => [t.value, t.label])
);

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? (type ? type.charAt(0).toUpperCase() + type.slice(1) : 'Other');
}

interface ItemGroup {
  type: string;
  label: string;
  items: Item[];
}

export function groupItemsByType(items: Item[]): ItemGroup[] {
  const buckets = new Map<string, Item[]>();
  for (const item of items) {
    const key = item.type || 'other';
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(item);
    } else {
      buckets.set(key, [item]);
    }
  }

  return Array.from(buckets.entries())
    .map(([type, groupItems]) => ({ type, label: typeLabel(type), items: groupItems }))
    .sort((a, b) => {
      const orderA = TYPE_GROUP_ORDER[a.type] ?? 99;
      const orderB = TYPE_GROUP_ORDER[b.type] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      return a.label.localeCompare(b.label);
    });
}

interface ItemPickerProps {
  selectedIds: Set<string>;
  onToggle: (item: Item) => void;
  hideNeedsWash?: boolean;
  filterType?: string;
  emptyMessage?: string;
  heightClass?: string;
}

export function ItemPicker({
  selectedIds,
  onToggle,
  hideNeedsWash = true,
  filterType,
  emptyMessage = 'No items found',
  heightClass = 'h-[360px]',
}: ItemPickerProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [accumulatedItems, setAccumulatedItems] = useState<Item[]>([]);
  const [accVersion, setAccVersion] = useState(0);
  const [grouped, setGrouped] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
      setAccumulatedItems([]);
      setAccVersion((v) => v + 1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const { data: itemsData, isLoading, isFetching } = useItems(
    {
      search: debouncedSearch || undefined,
      is_archived: false,
      type: filterType,
      needs_wash: hideNeedsWash ? false : undefined,
    },
    page,
    PAGE_SIZE
  );

  const hasMore = itemsData?.has_more ?? false;
  const totalItems = itemsData?.total ?? 0;

  useEffect(() => {
    if (itemsData?.items) {
      if (page === 1) {
        setAccumulatedItems(itemsData.items);
      } else {
        setAccumulatedItems((prev) => {
          const existingIds = new Set(prev.map((i) => i.id));
          const newItems = itemsData.items.filter(
            (i) => !existingIds.has(i.id)
          );
          return [...prev, ...newItems];
        });
      }
    }
  }, [itemsData?.items, page, accVersion]);

  const items = useMemo(
    () => (accumulatedItems.length > 0 ? accumulatedItems : itemsData?.items ?? []),
    [accumulatedItems, itemsData?.items]
  );

  const groups = useMemo(() => (grouped ? groupItemsByType(items) : null), [grouped, items]);

  const loadMore = useCallback(() => {
    if (hasMore && !isFetching) {
      setPage((p) => p + 1);
    }
  }, [hasMore, isFetching]);

  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const target = e.target as HTMLDivElement;
      const nearBottom =
        target.scrollHeight - target.scrollTop <= target.clientHeight + 100;
      if (nearBottom) loadMore();
    },
    [loadMore]
  );

  const renderItemButton = (item: Item) => {
    const isSelected = selectedIds.has(item.id);
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => onToggle(item)}
        className={cn(
          'relative aspect-square rounded-lg overflow-hidden border-2 transition-all',
          isSelected
            ? 'border-primary ring-2 ring-primary/20'
            : 'border-border hover:border-muted-foreground/50'
        )}
      >
        {item.thumbnail_url || item.image_url ? (
          <Image
            src={(item.thumbnail_url || item.image_url)!}
            alt={item.name || item.type}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 33vw, 20vw"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-muted">
            <span className="text-xs text-muted-foreground">
              {item.type}
            </span>
          </div>
        )}
        {isSelected && (
          <div className="absolute inset-0 bg-primary/30 flex items-center justify-center">
            <div className="rounded-full bg-primary p-1.5 shadow-lg">
              <Check className="h-4 w-4 text-primary-foreground" />
            </div>
          </div>
        )}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1.5">
          <span className="text-[10px] sm:text-xs text-white font-medium truncate block">
            {item.name ?? item.type}
          </span>
        </div>
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search wardrobe..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-9"
          />
        </div>
        <div className="flex rounded-md border overflow-hidden shrink-0">
          <button
            type="button"
            title="Group by clothing type"
            onClick={() => setGrouped(true)}
            className={cn(
              'h-9 px-2.5 flex items-center justify-center transition-colors',
              grouped ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'
            )}
          >
            <List className="h-4 w-4" />
          </button>
          <button
            type="button"
            title="Show all items"
            onClick={() => setGrouped(false)}
            className={cn(
              'h-9 px-2.5 flex items-center justify-center transition-colors border-l',
              !grouped ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'
            )}
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className={cn('overflow-y-auto py-2 -mx-1 px-1', heightClass)}
      >
        {groups ? (
          <div className="space-y-4">
            {groups.map((group) => (
              <div key={group.type}>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 sticky top-0 bg-background/95 backdrop-blur-sm py-0.5">
                  {group.label}{' '}
                  <span className="font-normal normal-case text-muted-foreground/70">
                    ({group.items.length})
                  </span>
                </h3>
                <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
                  {group.items.map(renderItemButton)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
            {items.map(renderItemButton)}
          </div>
        )}

        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {isFetching && !isLoading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mr-2" />
            <span className="text-xs text-muted-foreground">
              Loading more...
            </span>
          </div>
        )}

        {!isLoading && items.length === 0 && (
          <div className="text-center text-muted-foreground py-8">
            {debouncedSearch
              ? 'No items match your search'
              : emptyMessage}
          </div>
        )}

        {!isLoading && !hasMore && items.length > 0 && (
          <div className="text-center text-xs text-muted-foreground py-3">
            Showing all {totalItems} items
          </div>
        )}
      </div>
    </div>
  );
}
