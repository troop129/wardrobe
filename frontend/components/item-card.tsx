'use client';

import Image from 'next/image';
import { Heart, Droplets, Loader2, AlertCircle, RefreshCw, X } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { CLOTHING_COLORS, Item } from '@/lib/types';
import { formatWornAgo, getWornAgoColorClass } from '@/lib/utils';

interface ItemCardProps {
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

// Flat, borderless tile (no shadows/heavy chrome) - the thumbnail itself is
// expected to already sit on a clean white/cutout background (see the
// background-removal feature), so the tile just frames it with quiet padding
// instead of filling edge-to-edge.
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
  const colorInfo = CLOTHING_COLORS.find((c) => c.value === item.primary_color);
  const isProcessing = item.status === 'processing';
  const isError = item.status === 'error' && !errorDismissed;

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <button
      type="button"
      className={`group block w-full text-left border transition-colors ${
        selected ? 'border-foreground/60' : 'border-border hover:border-foreground/30'
      }`}
      onClick={onClick}
    >
      <div className="relative aspect-square bg-card p-3 sm:p-4">
        {item.thumbnail_url ? (
          <Image
            src={item.thumbnail_url}
            alt={item.name || item.type}
            fill
            className="object-contain p-2"
            sizes="(max-width: 640px) 50vw, (max-width: 768px) 33vw, (max-width: 1024px) 25vw, 20vw"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground text-xs uppercase tracking-wide">
            {item.type}
          </div>
        )}

        {/* Checkbox in top-left */}
        <div
          className={`absolute top-2 left-2 z-10 transition-opacity ${
            selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          }`}
          onClick={handleCheckboxClick}
        >
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onSelect(item.id, checked === true)}
            className="bg-background/80 backdrop-blur-sm"
          />
        </div>

        {/* Quiet monochrome status glyphs, top/bottom-right */}
        {item.favorite && (
          <Heart
            className="absolute top-2 right-2 z-10 h-3.5 w-3.5 fill-foreground/70 text-foreground/70"
            aria-label="Favorite"
          />
        )}
        {item.needs_wash && (
          <Droplets
            className="absolute bottom-2 right-2 z-10 h-3.5 w-3.5 text-muted-foreground"
            aria-label="Needs washing"
          />
        )}

        {isProcessing && (
          <div className="absolute inset-0 bg-background/70 flex flex-col items-center justify-center gap-2">
            <Loader2 className="h-5 w-5 text-foreground/70 animate-spin" />
            <span className="text-foreground/70 text-[11px] uppercase tracking-wide">Analyzing</span>
            {onCancelAnalysis && (
              <Button
                size="sm"
                variant="secondary"
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
          <div className="absolute inset-0 bg-background/85 flex flex-col items-center justify-center gap-2 p-2">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <span className="text-foreground/70 text-[11px] uppercase tracking-wide text-center">
              Analysis failed
            </span>
            <div className="flex gap-1.5">
              {onRetry && (
                <Button
                  size="sm"
                  variant="secondary"
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
                  variant="secondary"
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

      <div className="p-3 border-t border-border">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-medium text-sm truncate">{item.name || item.type}</p>
            <p className="text-xs text-muted-foreground capitalize">
              {item.type}
              {item.subtype && ` \u00b7 ${item.subtype}`}
              {item.tags?.logprobs_confidence != null &&
                ` \u00b7 ${Math.round(item.tags.logprobs_confidence * 100)}%`}
            </p>
          </div>
          {colorInfo && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    className="w-3.5 h-3.5 rounded-full border shrink-0 mt-0.5"
                    style={{ backgroundColor: colorInfo.hex }}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <p>{colorInfo.name}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        {item.last_worn_at ? (
          <p className={`text-xs mt-1 ${getWornAgoColorClass(item.last_worn_at, userTimezone)}`}>
            {formatWornAgo(item.last_worn_at, userTimezone)}
          </p>
        ) : item.wear_count > 0 ? (
          <p className="text-xs text-muted-foreground mt-1">
            Worn {item.wear_count} time{item.wear_count !== 1 ? 's' : ''}
          </p>
        ) : null}
        {item.ai_confidence !== undefined && item.ai_confidence > 0 && item.status === 'ready' && (
          <p className="text-xs text-muted-foreground mt-1">
            AI completeness: {Math.round(item.ai_confidence * 100)}%
          </p>
        )}
      </div>
    </button>
  );
}

export function ItemCardSkeleton() {
  return (
    <div className="border border-border">
      <Skeleton className="aspect-square rounded-none" />
      <div className="p-3 border-t border-border space-y-1.5">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}
