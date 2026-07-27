'use client';

import { cn } from '@/lib/utils';
import { CLOTHING_TYPES } from '@/lib/types';

interface WardrobeCategoryNavProps {
  activeType: string;
  onTypeChange: (typeId: string) => void;
  itemTypes?: { type: string; count: number }[];
}

const TYPE_LABELS = Object.fromEntries(
  CLOTHING_TYPES.map((t) => [t.value, t.label])
);

export function WardrobeCategoryNav({
  activeType,
  onTypeChange,
  itemTypes,
}: WardrobeCategoryNavProps) {
  const categories = [
    { id: 'all', label: 'All' },
    ...(itemTypes?.map((entry) => ({
      id: entry.type,
      label: TYPE_LABELS[entry.type] || entry.type.replace(/-/g, ' '),
    })) ?? []),
  ];

  return (
    <nav
      className="flex max-w-full overflow-x-auto border border-border/80 scrollbar-none"
      aria-label="Filter wardrobe by item type"
    >
      {categories.map((category) => (
        <button
          key={category.id}
          type="button"
          className={cn(
            'shrink-0 border-r border-border/80 px-4 py-2.5 text-[11px] font-medium uppercase tracking-[0.08em] transition-colors last:border-r-0',
            activeType === category.id
              ? 'bg-foreground text-background'
              : 'bg-transparent text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          )}
          onClick={() => onTypeChange(category.id)}
          aria-pressed={activeType === category.id}
        >
          {category.label}
        </button>
      ))}
    </nav>
  );
}
