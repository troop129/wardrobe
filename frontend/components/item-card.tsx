'use client';

import Image from 'next/image';
import { Loader2, AlertCircle, RefreshCw, X, Heart, Droplets } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Item } from '@/lib/types';
import { formatWornAgo, getWornAgoColorClass } from '@/lib/utils';
import { cn } from '@/lib/utils';

export interface ItemCardProps {
  item: Item;
  selected: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onRetry?: (id: string) => void;
  onCancelAnalysis?: (id: string) => void;
  onClick?: () => void;
  onDismissError?: (id: string) => void;
  errorDismissed?: boolean;
  userTimezone: string;
}

export function ItemCard({
  item,
  selected,
  onSelect,
  onRetry,
  onCancelAnalysis,
  onClick,
  onDismissError,
  errorDismissed,
  userTimezone,
}: ItemCardProps) {
  const isProcessing = item.status === 'processing';
  const isError = item.status === 'error' && !errorDismissed;

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <button
      type="button"
      className={cn(
        'group relative w-full text-left transition-colors',
        'border border-transparent hover:border-border/80',
        selected && 'border-foreground/30 bg-muted/30'
      )}
      onClick={onClick}
    >
      <div className="relative aspect-[4/5] bg-white p-3 sm:p-4">
        {item.thumbnail_url ? (
          <Image
            src={item.thumbnail_url}
            alt={item.name || item.type}
            fill
            className="object-contain p-2"
            sizes="(max-width: 640px) 50vw, (max-width: 768px) 33vw, (max-width: 1024px) 25vw, 180px"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs uppercase tracking-wide text-muted-foreground">
            {item.type}
          </div>
        )}

        <div
          className={cn(
            'absolute top-2 left-2 z-10 transition-opacity',
            selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          )}
          onClick={handleCheckboxClick}
        >
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onSelect(item.id, checked === true)}
            className="border-border bg-background/90"
          />
        </div>

        {item.favorite && (
          <Heart className="absolute top-2 right-2 z-10 h-3.5 w-3.5 fill-foreground/70 text-foreground/70" />
        )}
        {item.needs_wash && (
          <Droplets className="absolute bottom-2 right-2 z-10 h-3.5 w-3.5 text-muted-foreground" />
        )}

        {isProcessing && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/75 backdrop-blur-[1px]">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Analyzing
            </span>
            {onCancelAnalysis && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onCancelAnalysis(item.id);
                }}
              >
                <X className="h-3 w-3 mr-1" />
                Cancel
              </Button>
            )}
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/80 p-2">
            <AlertCircle className="h-5 w-5 text-destructive/80" />
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Failed
            </span>
            <div className="flex gap-1.5">
              {onRetry && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRetry(item.id);
                  }}
                >
                  <RefreshCw className="h-3 w-3 mr-1" />
                  Retry
                </Button>
              )}
              {onDismissError && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  title="Dismiss"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDismissError(item.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="px-1 pb-3 pt-2">
        <p className="truncate text-sm font-medium leading-tight">
          {item.name || item.type}
        </p>
        {item.last_worn_at ? (
          <p className={cn('mt-0.5 text-[11px]', getWornAgoColorClass(item.last_worn_at, userTimezone))}>
            {formatWornAgo(item.last_worn_at, userTimezone)}
          </p>
        ) : item.wear_count > 0 ? (
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Worn {item.wear_count} time{item.wear_count !== 1 ? 's' : ''}
          </p>
        ) : (
          <p className="mt-0.5 text-[11px] capitalize text-muted-foreground">
            {item.subtype ? `${item.type} · ${item.subtype}` : item.type}
          </p>
        )}
      </div>
    </button>
  );
}

export function ItemCardSkeleton() {
  return (
    <div className="border border-transparent">
      <Skeleton className="aspect-[4/5] bg-white" />
      <div className="space-y-1 px-1 pb-3 pt-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}
