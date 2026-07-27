'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Plus, Search, Grid3X3, Loader2, AlertCircle, ArrowUpDown, SlidersHorizontal, Heart, Droplets, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AddItemDialog } from '@/components/add-item-dialog';
import { ItemDetailDialog } from '@/components/item-detail-dialog';
import { ItemCard, ItemCardSkeleton } from '@/components/item-card';
import { BulkActionToolbar, BulkSelection } from '@/components/bulk-action-toolbar';
import { useItems, useItem, useItemTypes, useReanalyzeItem, useCancelAnalysis, useBulkDeleteItems, useBulkReanalyzeItems, useBulkRemoveBackgroundItems, BulkOperationParams } from '@/lib/hooks/use-items';
import { useUserProfile } from '@/lib/hooks/use-user';
import { useFeatures } from '@/lib/hooks/use-features';
import { CLOTHING_TYPES } from '@/lib/types';
import { toast } from 'sonner';

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

const SORT_OPTIONS = [
  { label: 'Newest first', value: 'created_at', order: 'desc' as const },
  { label: 'Oldest first', value: 'created_at', order: 'asc' as const },
  { label: 'Recently worn', value: 'last_worn', order: 'desc' as const },
  { label: 'Least recently worn', value: 'last_worn', order: 'asc' as const },
  { label: 'Most worn', value: 'wear_count', order: 'desc' as const },
  { label: 'Least worn', value: 'wear_count', order: 'asc' as const },
  { label: 'Name A–Z', value: 'name', order: 'asc' as const },
  { label: 'Name Z–A', value: 'name', order: 'desc' as const },
] as const;

function EmptyWardrobe({ onAddClick }: { onAddClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="rounded-full bg-muted p-6 mb-4">
        <Grid3X3 className="h-12 w-12 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">Your wardrobe is empty</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">
        Add your first clothing item to start getting personalized outfit
        suggestions.
      </p>
      <Button onClick={onAddClick}>
        <Plus className="mr-2 h-4 w-4" />
        Add First Item
      </Button>
    </div>
  );
}

export default function WardrobePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: userProfile } = useUserProfile();
  const userTimezone = userProfile?.timezone || 'UTC';
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [selection, setSelection] = useState<BulkSelection>({
    mode: 'none',
    selectedIds: new Set(),
    excludedIds: new Set(),
  });
  const [detailItemId, setDetailItemId] = useState<string | null>(null);
  const [search, setSearch] = useState(() => searchParams.get('search') ?? '');
  const [typeFilter, setTypeFilter] = useState<string>(() => searchParams.get('type') ?? 'all');
  const [sortIndex, setSortIndex] = useState(() => {
    const raw = Number(searchParams.get('sort'));
    return Number.isInteger(raw) && raw >= 0 && raw < SORT_OPTIONS.length ? raw : 0;
  });
  const [needsWash, setNeedsWash] = useState<boolean | undefined>(() =>
    searchParams.get('needsWash') === 'true' ? true : undefined
  );
  const [favoriteFilter, setFavoriteFilter] = useState<boolean | undefined>(() =>
    searchParams.get('favorite') === 'true' ? true : undefined
  );
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(() => {
    const raw = Number(searchParams.get('page'));
    return Number.isInteger(raw) && raw > 0 ? raw : 1;
  });
  const [pageSize, setPageSize] = useState(() => {
    const raw = Number(searchParams.get('pageSize'));
    return PAGE_SIZE_OPTIONS.includes(raw) ? raw : 20;
  });
  const [dismissedErrors, setDismissedErrors] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set();
    try {
      const raw = window.sessionStorage.getItem('wardrobe-dismissed-errors');
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch {
      return new Set();
    }
  });

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        'wardrobe-dismissed-errors',
        JSON.stringify(Array.from(dismissedErrors))
      );
    } catch {
      // because sessionStorage can be unavailable (private browsing, quota), dismissal just won't persist
    }
  }, [dismissedErrors]);

  // Open item detail dialog from URL param (e.g. ?item=uuid from outfit pages)
  useEffect(() => {
    const itemParam = searchParams.get('item');
    if (itemParam && !detailItemId) {
      setDetailItemId(itemParam);
    }
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep filters/page/sort in the URL so a refresh or shared link preserves them
  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());

    if (search) params.set('search', search); else params.delete('search');
    if (typeFilter !== 'all') params.set('type', typeFilter); else params.delete('type');
    if (sortIndex !== 0) params.set('sort', String(sortIndex)); else params.delete('sort');
    if (needsWash) params.set('needsWash', 'true'); else params.delete('needsWash');
    if (favoriteFilter) params.set('favorite', 'true'); else params.delete('favorite');
    if (page !== 1) params.set('page', String(page)); else params.delete('page');
    if (pageSize !== 20) params.set('pageSize', String(pageSize)); else params.delete('pageSize');

    const next = params.toString();
    if (next !== searchParams.toString()) {
      router.replace(next ? `/dashboard/wardrobe?${next}` : '/dashboard/wardrobe', { scroll: false });
    }
  }, [search, typeFilter, sortIndex, needsWash, favoriteFilter, page, pageSize, searchParams, router]);

  const sortOption = SORT_OPTIONS[sortIndex];

  const filters = {
    search: search || undefined,
    type: typeFilter !== 'all' ? typeFilter : undefined,
    needs_wash: needsWash,
    favorite: favoriteFilter,
    is_archived: false,
    sort_by: sortOption.value,
    sort_order: sortOption.order,
  };

  const activeFilterCount = [
    needsWash !== undefined,
    favoriteFilter !== undefined,
    typeFilter !== 'all',
  ].filter(Boolean).length;

  // Fetch items with automatic polling (faster when items are processing)
  const { data, isLoading, error } = useItems(filters, page, pageSize);
  const { data: itemTypes } = useItemTypes();
  const { data: features } = useFeatures();
  const reanalyze = useReanalyzeItem();
  const cancelAnalysis = useCancelAnalysis();
  const bulkDelete = useBulkDeleteItems();
  const bulkReanalyze = useBulkReanalyzeItems();
  const bulkRemoveBackground = useBulkRemoveBackgroundItems();
  const [bulkProgress, setBulkProgress] = useState<{
    label: string;
    value: number;
  } | null>(null);

  const items = data?.items || [];
  const total = data?.total || 0;

  // Always fetch the open item. The list can hold a stale processing snapshot
  // after an AI job completed, which would otherwise leave its overlay stuck.
  const listItem = detailItemId ? items.find((i) => i.id === detailItemId) || null : null;
  const { data: fetchedItem } = useItem(detailItemId ?? '');
  const detailItem = fetchedItem || listItem || null;

  // Count items being processed or with errors
  const processingCount = items.filter((i) => i.status === 'processing').length;
  const errorCount = items.filter(
    (i) => i.status === 'error' && !dismissedErrors.has(`${i.id}:${i.updated_at}`)
  ).length;

  // Clear selection when filters change (but not page - allow cross-page selection)
  useEffect(() => {
    setSelection({ mode: 'none', selectedIds: new Set(), excludedIds: new Set() });
  }, [search, typeFilter, needsWash, favoriteFilter, sortIndex]);

  // Soft progress for bulk cleanup / re-analyze while the queue request is in flight
  // and while items remain processing.
  useEffect(() => {
    const cleaning = bulkRemoveBackground.isPending;
    const reanalyzing = bulkReanalyze.isPending || processingCount > 0;
    if (!cleaning && !reanalyzing) {
      setBulkProgress(null);
      return;
    }
    setBulkProgress((prev) =>
      prev ?? {
        label: cleaning
          ? 'Queueing background cleanup…'
          : processingCount > 0
            ? `Analyzing ${processingCount} item${processingCount !== 1 ? 's' : ''}…`
            : 'Queueing re-analysis…',
        value: 12,
      }
    );
    const id = window.setInterval(() => {
      setBulkProgress((prev) => {
        if (!prev) return prev;
        const nextLabel = cleaning
          ? 'Cleaning up backgrounds…'
          : processingCount > 0
            ? `Analyzing ${processingCount} item${processingCount !== 1 ? 's' : ''}…`
            : prev.label;
        return {
          label: nextLabel,
          value: Math.min(cleaning ? 90 : 85, prev.value + 4),
        };
      });
    }, 700);
    return () => window.clearInterval(id);
  }, [bulkRemoveBackground.isPending, bulkReanalyze.isPending, processingCount]);

  const handleRetry = (itemId: string) => {
    reanalyze.mutate(itemId);
  };

  const handleCancelAnalysis = (itemId: string) => {
    cancelAnalysis.mutate(itemId);
  };

  const handleDismissError = (itemId: string) => {
    const item = items.find((i) => i.id === itemId);
    if (!item) return;
    setDismissedErrors((prev) => new Set(prev).add(`${item.id}:${item.updated_at}`));
  };

  const handleSelect = (id: string, checked: boolean) => {
    setSelection((prev) => {
      if (prev.mode === 'all') {
        // In "select all" mode, toggle exclusion
        const next = new Set(prev.excludedIds);
        if (checked) {
          next.delete(id); // Remove from excluded = selected
        } else {
          next.add(id); // Add to excluded = deselected
        }
        return { ...prev, excludedIds: next };
      } else {
        // In "some" or "none" mode, toggle selection
        const next = new Set(prev.selectedIds);
        if (checked) {
          next.add(id);
        } else {
          next.delete(id);
        }
        return { mode: next.size > 0 ? 'some' : 'none', selectedIds: next, excludedIds: new Set() };
      }
    });
  };

  const handleSelectPage = () => {
    setSelection((prev) => {
      const pageFullySelected =
        (prev.mode === 'all' && prev.excludedIds.size === 0) ||
        (prev.mode === 'some' && prev.selectedIds.size === items.length && items.length > 0);
      if (pageFullySelected) {
        return { mode: 'none', selectedIds: new Set(), excludedIds: new Set() };
      }
      return { mode: 'some', selectedIds: new Set(items.map((i) => i.id)), excludedIds: new Set() };
    });
  };

  const handleSelectAllMatching = () => {
    setSelection({ mode: 'all', selectedIds: new Set(), excludedIds: new Set() });
  };

  const handleClearSelection = () => {
    setSelection({ mode: 'none', selectedIds: new Set(), excludedIds: new Set() });
  };

  // Build bulk operation params from selection state
  const getBulkParams = (): BulkOperationParams => {
    if (selection.mode === 'all') {
      return {
        select_all: true,
        excluded_ids: Array.from(selection.excludedIds),
        filters: {
          type: typeFilter !== 'all' ? typeFilter : undefined,
          search: search || undefined,
          needs_wash: needsWash,
          favorite: favoriteFilter,
          is_archived: false,
        },
      };
    } else {
      return {
        item_ids: Array.from(selection.selectedIds),
      };
    }
  };

  const handleBulkDelete = async () => {
    const params = getBulkParams();
    try {
      const result = await bulkDelete.mutateAsync(params);
      toast.success(`Deleted ${result.deleted} items`);
      if (result.failed > 0) {
        toast.error(`Failed to delete ${result.failed} items`);
      }
      handleClearSelection();
    } catch {
      toast.error('Failed to delete items');
    }
  };

  const handleBulkReanalyze = async () => {
    const params = getBulkParams();
    try {
      const result = await bulkReanalyze.mutateAsync(params);
      if (result.queued > 20) {
        toast.success(`Queued ${result.queued} items for re-analysis. This may take a while.`);
      } else {
        toast.success(`Queued ${result.queued} items for re-analysis`);
      }
      if (result.failed > 0) {
        toast.error(`Failed to queue ${result.failed} items`);
      }
      handleClearSelection();
    } catch {
      toast.error('Failed to queue items for re-analysis');
    }
  };

  const handleBulkRemoveBackground = async () => {
    const params = getBulkParams();
    try {
      const result = await bulkRemoveBackground.mutateAsync(params);
      toast.success(`Queued ${result.queued} item${result.queued !== 1 ? 's' : ''} for background cleanup`);
      if (result.failed > 0) {
        toast.error(`Failed to queue ${result.failed} items`);
      }
      handleClearSelection();
    } catch {
      toast.error('Failed to queue background cleanup');
    }
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center justify-between sm:justify-start gap-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
                My Wardrobe
              </p>
              <h1 className="text-lg font-medium tracking-tight">
                {total} item{total !== 1 ? 's' : ''}
              </h1>
            </div>
            <Button onClick={() => setAddDialogOpen(true)} className="sm:hidden" size="sm">
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          {(processingCount > 0 || errorCount > 0) && (
            <div className="flex items-center gap-2 mt-2">
              {processingCount > 0 && (
                <Badge variant="secondary" className="gap-1 text-xs">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {processingCount} analyzing
                </Badge>
              )}
              {errorCount > 0 && (
                <Badge variant="destructive" className="gap-1 text-xs">
                  <AlertCircle className="h-3 w-3" />
                  {errorCount} failed
                </Badge>
              )}
            </div>
          )}
        </div>
        <Button onClick={() => setAddDialogOpen(true)} className="hidden sm:flex">
          <Plus className="mr-2 h-4 w-4" />
          Add Item
        </Button>
      </div>

      {/* Category filter, always visible - horizontally scrollable so it holds up
          with any number of item types instead of wrapping into a wall of pills */}
      <div className="flex overflow-x-auto -mx-1 px-1 scrollbar-none">
        <button
          type="button"
          onClick={() => {
            setTypeFilter('all');
            setPage(1);
          }}
          className={`shrink-0 border px-4 py-2 text-[11px] font-medium uppercase tracking-wider transition-colors ${
            typeFilter === 'all'
              ? 'bg-foreground text-background border-foreground'
              : 'text-muted-foreground border-border hover:bg-muted hover:text-foreground'
          }`}
        >
          All
        </button>
        {(itemTypes ?? []).map((t) => {
          const label = CLOTHING_TYPES.find((ct) => ct.value === t.type)?.label ?? t.type;
          return (
            <button
              key={t.type}
              type="button"
              onClick={() => {
                setTypeFilter(t.type);
                setPage(1);
              }}
              className={`shrink-0 -ml-px border px-4 py-2 text-[11px] font-medium uppercase tracking-wider transition-colors ${
                typeFilter === t.type
                  ? 'bg-foreground text-background border-foreground'
                  : 'text-muted-foreground border-border hover:bg-muted hover:text-foreground'
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="space-y-3">
        {/* Main row: search + sort + filter toggle */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search items..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Select
              value={String(sortIndex)}
              onValueChange={(v) => {
                setSortIndex(Number(v));
                setPage(1);
              }}
            >
              <SelectTrigger className="w-full sm:w-[180px]">
                <ArrowUpDown className="h-3.5 w-3.5 mr-1.5 shrink-0" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((opt, i) => (
                  <SelectItem key={i} value={String(i)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant={showFilters || activeFilterCount > 0 ? 'default' : 'outline'}
              size="icon"
              className="shrink-0 relative"
              onClick={() => setShowFilters((v) => !v)}
            >
              <SlidersHorizontal className="h-4 w-4" />
              {activeFilterCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-primary text-[10px] font-bold text-primary-foreground flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </div>
        </div>

        {/* Expandable filter row */}
        {showFilters && (
          <div className="flex flex-wrap gap-2 items-center p-3 border bg-muted/30">
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                setPageSize(Number(value));
                setPage(1);
              }}
            >
              <SelectTrigger className="w-[130px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size} per page
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              variant={needsWash === true ? 'default' : 'outline'}
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={() => {
                setNeedsWash(needsWash === true ? undefined : true);
                setPage(1);
              }}
            >
              <Droplets className="h-3.5 w-3.5" />
              Needs wash
            </Button>

            <Button
              variant={favoriteFilter === true ? 'default' : 'outline'}
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={() => {
                setFavoriteFilter(favoriteFilter === true ? undefined : true);
                setPage(1);
              }}
            >
              <Heart className="h-3.5 w-3.5" />
              Favorites
            </Button>

            {activeFilterCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs gap-1 ml-auto"
                onClick={() => {
                  setTypeFilter('all');
                  setNeedsWash(undefined);
                  setFavoriteFilter(undefined);
                  setPage(1);
                }}
              >
                <X className="h-3 w-3" />
                Clear filters
              </Button>
            )}
          </div>
        )}
      </div>

      {bulkProgress && (
        <div className="rounded-lg border bg-card px-4 py-3 space-y-2">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{bulkProgress.label}</span>
            <span className="text-muted-foreground tabular-nums">{bulkProgress.value}%</span>
          </div>
          <Progress value={bulkProgress.value} className="h-1.5" />
        </div>
      )}

      {error ? (
        <div className="text-center py-8">
          <p className="text-destructive">
            Failed to load items. Please try again.
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => window.location.reload()}
          >
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <ItemCardSkeleton key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        search || typeFilter !== 'all' || needsWash !== undefined || favoriteFilter !== undefined ? (
          <div className="text-center py-8">
            <p className="text-muted-foreground">
              No items found matching your filters.
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => {
                setSearch('');
                setTypeFilter('all');
                setNeedsWash(undefined);
                setFavoriteFilter(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          </div>
        ) : (
          <EmptyWardrobe onAddClick={() => setAddDialogOpen(true)} />
        )
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 pb-20">
          {items.map((item) => {
            // Determine if item is selected based on selection mode
            const isSelected = selection.mode === 'all'
              ? !selection.excludedIds.has(item.id)
              : selection.selectedIds.has(item.id);
            return (
              <ItemCard
                key={item.id}
                item={item}
                selected={isSelected}
                onSelect={handleSelect}
                onRetry={handleRetry}
                onCancelAnalysis={handleCancelAnalysis}
                onClick={() => setDetailItemId(item.id)}
                onDismissError={handleDismissError}
                errorDismissed={dismissedErrors.has(`${item.id}:${item.updated_at}`)}
                userTimezone={userTimezone}
              />
            );
          })}
        </div>
      )}

      <BulkActionToolbar
        selection={selection}
        totalItems={total}
        pageItems={items.length}
        onSelectAll={handleSelectPage}
        onSelectAllMatching={handleSelectAllMatching}
        onClear={handleClearSelection}
        onDelete={handleBulkDelete}
        onReanalyze={handleBulkReanalyze}
        onRemoveBackground={features?.background_removal ? handleBulkRemoveBackground : undefined}
        isDeleting={bulkDelete.isPending}
        isReanalyzing={bulkReanalyze.isPending}
        isRemovingBackground={bulkRemoveBackground.isPending}
        itemLabel="items"
        deleteWarningSuffix=" and their images"
        page={page}
        pageSize={pageSize}
        onPageChange={handlePageChange}
      />

      <AddItemDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} />
      <ItemDetailDialog
        item={detailItem}
        open={!!detailItemId}
        onOpenChange={(open) => {
          if (!open) {
            setDetailItemId(null);
            // Clear only the ?item= param, keep filters/page/sort intact
            if (searchParams.has('item')) {
              const params = new URLSearchParams(searchParams.toString());
              params.delete('item');
              const next = params.toString();
              router.replace(next ? `/dashboard/wardrobe?${next}` : '/dashboard/wardrobe', { scroll: false });
            }
          }
        }}
      />
    </div>
  );
}
