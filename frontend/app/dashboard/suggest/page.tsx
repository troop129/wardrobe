'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useSession } from 'next-auth/react';
import {
  Briefcase,
  Shirt,
  Heart,
  Dumbbell,
  TreePine,
  Sparkles,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Cloud,
  Sun,
  CloudRain,
  Loader2,
  AlertCircle,
  Thermometer,
  Droplets,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MapPin,
  Wind,
  GlassWater,
  Cloudy,
  CloudSun,
  Snowflake,
  CalendarDays,
  CloudLightning,
  Link2,
  MessageCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { api, ApiError, setAccessToken } from '@/lib/api';
import { Item, OCCASIONS, Outfit, SuggestRequest } from '@/lib/types';
import { useItems } from '@/lib/hooks/use-items';
import { useWeather, Weather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { cn, parseDateString } from '@/lib/utils';
import { TempUnit, formatTemp, displayValue, toF, toCelsius } from '@/lib/temperature';
import { toast } from 'sonner';
import { ITEM_ROLE } from '@/lib/studio/canonical-order';

// Map occasion values to icons and colors
const OCCASION_CONFIG: Record<string, { icon: React.ReactNode; color: string }> = {
  casual: { icon: <Shirt className="h-4 w-4" />, color: 'hover:border-blue-400 hover:bg-blue-50 data-[selected=true]:border-blue-500 data-[selected=true]:bg-blue-50 data-[selected=true]:text-blue-700' },
  office: { icon: <Briefcase className="h-4 w-4" />, color: 'hover:border-slate-400 hover:bg-slate-50 data-[selected=true]:border-slate-500 data-[selected=true]:bg-slate-50 data-[selected=true]:text-slate-700' },
  formal: { icon: <GlassWater className="h-4 w-4" />, color: 'hover:border-purple-400 hover:bg-purple-50 data-[selected=true]:border-purple-500 data-[selected=true]:bg-purple-50 data-[selected=true]:text-purple-700' },
  date: { icon: <Heart className="h-4 w-4" />, color: 'hover:border-rose-400 hover:bg-rose-50 data-[selected=true]:border-rose-500 data-[selected=true]:bg-rose-50 data-[selected=true]:text-rose-700' },
  sporty: { icon: <Dumbbell className="h-4 w-4" />, color: 'hover:border-orange-400 hover:bg-orange-50 data-[selected=true]:border-orange-500 data-[selected=true]:bg-orange-50 data-[selected=true]:text-orange-700' },
  outdoor: { icon: <TreePine className="h-4 w-4" />, color: 'hover:border-green-400 hover:bg-green-50 data-[selected=true]:border-green-500 data-[selected=true]:bg-green-50 data-[selected=true]:text-green-700' },
};

// Weather condition to icon mapping
function getWeatherIcon(condition: string, isDay: boolean) {
  const c = condition.toLowerCase();
  if (c.includes('rain') || c.includes('drizzle')) return <CloudRain className="h-8 w-8" />;
  if (c.includes('snow')) return <Snowflake className="h-8 w-8" />;
  if (c.includes('thunder') || c.includes('storm')) return <CloudLightning className="h-8 w-8" />;
  if (c.includes('cloud') && c.includes('part')) return <CloudSun className="h-8 w-8" />;
  if (c.includes('cloud') || c.includes('overcast')) return <Cloudy className="h-8 w-8" />;
  return isDay ? <Sun className="h-8 w-8" /> : <Cloud className="h-8 w-8" />;
}

// Get time-based greeting
function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// Get weather-based outfit hint
function getWeatherHint(weather: Weather): string {
  const temp = weather.temperature;
  const condition = weather.condition.toLowerCase();

  if (weather.precipitation_chance > 50) return 'Bring an umbrella or rain jacket';
  if (temp < 10) return 'Layer up - it\'s quite cold';
  if (temp < 18) return 'A light jacket would be perfect';
  if (temp > 28) return 'Keep it light and breathable';
  if (condition.includes('wind')) return 'Consider something windproof';
  return 'Great weather for any style';
}

interface WeatherOverride {
  temperature: number;
  condition: 'sunny' | 'cloudy' | 'rainy';
}

function WeatherCard({ weather, isLoading, temperatureUnit }: { weather?: Weather; isLoading: boolean; temperatureUnit: TempUnit }) {
  if (isLoading) {
    return (
      <Card className="border-muted">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <Skeleton className="h-16 w-16 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!weather) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center">
              <MapPin className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <p className="font-medium">Location not set</p>
              <p className="text-sm text-muted-foreground">
                Set your location in settings for weather-aware suggestions
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center text-foreground">
              {getWeatherIcon(weather.condition, weather.is_day)}
            </div>
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-4xl font-semibold tracking-tight">{displayValue(weather.temperature, temperatureUnit)}</span>
                <span className="text-lg text-muted-foreground">{temperatureUnit === 'fahrenheit' ? '°F' : '°C'}</span>
              </div>
              <p className="text-sm text-muted-foreground capitalize">{weather.condition}</p>
            </div>
          </div>
          <div className="text-right text-sm text-muted-foreground space-y-1">
            <div className="flex items-center gap-1.5 justify-end">
              <Thermometer className="h-3.5 w-3.5" />
              <span>Feels {displayValue(weather.feels_like, temperatureUnit)}°</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Droplets className="h-3.5 w-3.5" />
              <span>{weather.precipitation_chance}% rain</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Wind className="h-3.5 w-3.5" />
              <span>{Math.round(weather.wind_speed)} km/h</span>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            {getWeatherHint(weather)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function OccasionChips({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (occasion: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {OCCASIONS.map((occasion) => {
        const config = OCCASION_CONFIG[occasion.value];
        return (
          <button
            key={occasion.value}
            onClick={() => onSelect(occasion.value)}
            data-selected={selected === occasion.value}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-full border-2 transition-all',
              'border-muted bg-background',
              config?.color || 'hover:border-primary hover:bg-primary/5',
              'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary/50'
            )}
          >
            {config?.icon}
            <span className="text-sm font-medium">{occasion.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function WeatherOverrideSection({
  weather,
  onChange,
  temperatureUnit,
}: {
  weather: WeatherOverride | null;
  onChange: (weather: WeatherOverride | null) => void;
  temperatureUnit: TempUnit;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const conditions = [
    { value: 'sunny', icon: <Sun className="h-4 w-4" />, label: 'Sunny' },
    { value: 'cloudy', icon: <Cloud className="h-4 w-4" />, label: 'Cloudy' },
    { value: 'rainy', icon: <CloudRain className="h-4 w-4" />, label: 'Rainy' },
  ] as const;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
          <span>{weather ? 'Weather override active' : 'Override weather'}</span>
          {weather && (
            <Badge variant="secondary" className="text-xs">
              {weather.condition} {formatTemp(weather.temperature, temperatureUnit)}
            </Badge>
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-4">
        <div className="space-y-4 p-4 rounded-lg bg-muted/50">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Condition</span>
            {weather && (
              <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
                Reset
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            {conditions.map((c) => (
              <button
                key={c.value}
                onClick={() =>
                  onChange({
                    temperature: weather?.temperature ?? 20,
                    condition: c.value,
                  })
                }
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg border transition-all',
                  weather?.condition === c.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-muted bg-background hover:border-primary/50'
                )}
              >
                {c.icon}
                <span className="text-sm">{c.label}</span>
              </button>
            ))}
          </div>
          {weather && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Temperature</span>
              <input
                type="range"
                min={temperatureUnit === 'fahrenheit' ? 14 : -10}
                max={temperatureUnit === 'fahrenheit' ? 104 : 40}
                value={temperatureUnit === 'fahrenheit' ? Math.round(toF(weather.temperature)) : weather.temperature}
                onChange={(e) => {
                  const raw = parseInt(e.target.value);
                  onChange({ ...weather, temperature: temperatureUnit === 'fahrenheit' ? Math.round(toCelsius(raw)) : raw });
                }}
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-medium w-14 text-right">{formatTemp(weather.temperature, temperatureUnit)}</span>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function OutfitGenerationProgress() {
  const [stage, setStage] = useState(0);
  const stages = [
    'Looking through your wardrobe…',
    'Matching colours, layers, and the weather…',
    'Putting your look together…',
  ];

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStage((current) => (current + 1) % stages.length);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [stages.length]);

  return (
    <Card aria-live="polite" aria-busy="true" className="overflow-hidden">
      <CardContent className="p-6 space-y-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="h-6 w-6 animate-pulse text-primary" />
          </div>
          <div>
            <h2 className="font-semibold">Creating your outfit</h2>
            <p className="mt-1 text-sm text-muted-foreground">{stages[stage]}</p>
          </div>
        </div>
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="h-5 w-2/5" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <div className="grid grid-cols-3 gap-3 pt-2">
            <Skeleton className="aspect-square rounded-xl" />
            <Skeleton className="aspect-square rounded-xl" />
            <Skeleton className="aspect-square rounded-xl" />
          </div>
        </div>
        <p className="text-center text-xs text-muted-foreground">
          This can take a little while when the AI is busy. Keep this page open.
        </p>
      </CardContent>
    </Card>
  );
}

function itemSlotLabel(type: string) {
  const role = ITEM_ROLE[type];
  if (type === 'cologne') return 'Fragrance';
  return {
    full_body: 'One piece',
    base_top: 'Top',
    mid_layer: 'Mid layer',
    outer_layer: 'Outer layer',
    bottom: 'Bottom',
    footwear: 'Shoes',
    accessory: 'Accessory',
    socks: 'Socks',
    neckwear: 'Neckwear',
  }[role] || type;
}

function StackedOutfitEditor({
  outfit,
  wardrobeItems,
  disabled,
  onSwap,
}: {
  outfit: Outfit;
  wardrobeItems: Item[];
  disabled: boolean;
  onSwap: (currentId: string, replacementId: string) => Promise<void>;
}) {
  const alternativesFor = (current: Outfit['items'][number]) => {
    const currentRole = ITEM_ROLE[current.type];
    return wardrobeItems.filter((candidate) => {
      if (candidate.status !== 'ready' || candidate.needs_wash || candidate.is_archived) return false;
      if (current.type === 'cologne') return candidate.type === 'cologne';
      return ITEM_ROLE[candidate.type] === currentRole;
    });
  };

  const move = async (current: Outfit['items'][number], direction: -1 | 1) => {
    const alternatives = alternativesFor(current);
    if (alternatives.length < 2) return;
    const index = alternatives.findIndex((candidate) => candidate.id === current.id);
    const nextIndex = ((index < 0 ? 0 : index) + direction + alternatives.length) % alternatives.length;
    await onSwap(current.id, alternatives[nextIndex].id);
  };

  return (
    <div className="space-y-2">
      {outfit.items.map((item) => {
        const alternatives = alternativesFor(item);
        const canFlip = alternatives.length > 1;
        return (
          <div key={item.id} className="grid grid-cols-[44px_minmax(0,1fr)_44px] items-center gap-2 rounded-2xl border bg-muted/20 p-2">
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Previous ${itemSlotLabel(item.type)}`}
              disabled={disabled || !canFlip}
              onClick={() => move(item, -1)}
            >
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <div className="min-w-0">
              <div className="mb-1 flex items-center justify-between gap-2 px-1">
                <Badge variant="secondary" className="text-[11px] uppercase tracking-wide">
                  {itemSlotLabel(item.type)}
                </Badge>
                <span className="truncate text-xs text-muted-foreground">
                  {canFlip ? `${alternatives.length} clean options` : 'Only available option'}
                </span>
              </div>
              <Link href={`/dashboard/wardrobe?item=${item.id}`} className="group block">
                <div className="relative mx-auto h-36 w-full max-w-sm overflow-hidden rounded-xl bg-background sm:h-44">
                  {item.thumbnail_url || item.image_url ? (
                    <Image
                      src={item.thumbnail_url || item.image_url || ''}
                      alt={item.name || item.type}
                      fill
                      className="object-contain transition-transform group-hover:scale-[1.03]"
                      sizes="(max-width: 640px) 70vw, 420px"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center"><Shirt className="h-10 w-10 text-muted-foreground/40" /></div>
                  )}
                </div>
                <div className="mt-1 text-center">
                  <p className="truncate text-sm font-medium">{item.name || item.type}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {[item.brand, item.primary_color].filter(Boolean).join(' · ') || item.type}
                  </p>
                </div>
              </Link>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Next ${itemSlotLabel(item.type)}`}
              disabled={disabled || !canFlip}
              onClick={() => move(item, 1)}
            >
              <ChevronRight className="h-5 w-5" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function OutfitResult({
  outfit,
  occasion,
  temperatureUnit,
  onAccept,
  onReject,
  onTryAnother,
  onNewRequest,
  isResponding,
  wardrobeItems,
  onSwap,
  onRefine,
  onKeepTogether,
}: {
  outfit: Outfit;
  occasion: string;
  temperatureUnit: TempUnit;
  onAccept: () => void;
  onReject: () => void;
  onTryAnother: () => void;
  onNewRequest: () => void;
  isResponding: boolean;
  wardrobeItems: Item[];
  onSwap: (currentId: string, replacementId: string) => Promise<void>;
  onRefine: (message: string) => Promise<string>;
  onKeepTogether: (itemIds: string[]) => Promise<void>;
}) {
  const [refinement, setRefinement] = useState('');
  const [assistantReply, setAssistantReply] = useState('');
  const [pairDialogOpen, setPairDialogOpen] = useState(false);
  const [selectedPairIds, setSelectedPairIds] = useState<string[]>([]);

  const submitRefinement = async () => {
    if (!refinement.trim() || isResponding) return;
    const reply = await onRefine(refinement.trim());
    setAssistantReply(reply);
    setRefinement('');
  };

  const saveSelectedPair = async () => {
    if (selectedPairIds.length !== 2 || isResponding) return;
    await onKeepTogether(selectedPairIds);
    setPairDialogOpen(false);
    setSelectedPairIds([]);
  };

  return (
    <div className="space-y-6">
      {/* Header with occasion and new request */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="capitalize text-sm px-3 py-1">
            {occasion}
          </Badge>
          {outfit.scheduled_for && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CalendarDays className="h-3 w-3" />
              {parseDateString(outfit.scheduled_for).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={onNewRequest}>
          Start over
        </Button>
      </div>

      {/* Weather info */}
      {outfit.weather && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-1.5">
            <Thermometer className="h-4 w-4" />
            <span>{formatTemp(outfit.weather.temperature, temperatureUnit)}</span>
            <span className="text-xs opacity-70">(feels {displayValue(outfit.weather.feels_like, temperatureUnit)}°)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Droplets className="h-4 w-4" />
            <span>{outfit.weather.precipitation_chance}% rain</span>
          </div>
          <Badge variant="outline" className="capitalize">
            {outfit.weather.condition}
          </Badge>
        </div>
      )}

      {/* Outfit Card */}
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-r from-primary/10 to-primary/5 p-4 border-b">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Your Outfit</h3>
          </div>
          {outfit.reasoning && (
            <p className="mt-2 text-base font-medium text-foreground">{outfit.reasoning}</p>
          )}
          {outfit.highlights && outfit.highlights.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {outfit.highlights.map((highlight, index) => (
                <li key={index} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="text-primary mt-0.5">•</span>
                  <span>{highlight}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <CardContent className="p-4">
          <StackedOutfitEditor
            outfit={outfit}
            wardrobeItems={wardrobeItems}
            disabled={isResponding}
            onSwap={onSwap}
          />

          {outfit.style_notes && (
            <div className="mt-4 p-3 bg-muted rounded-lg border">
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Tip:</span> {outfit.style_notes}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-primary" />
            <div>
              <p className="text-sm font-medium">Tweak this outfit</p>
              <p className="text-xs text-muted-foreground">Runs locally: try “different shoes”, “add a layer”, “no cologne”, or “use the blue Nike jacket”.</p>
            </div>
          </div>
          <Textarea
            value={refinement}
            onChange={(event) => setRefinement(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void submitRefinement();
              }
            }}
            placeholder="What would you change?"
            rows={2}
            disabled={isResponding}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="secondary" size="sm" onClick={submitRefinement} disabled={!refinement.trim() || isResponding}>
              {isResponding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-2 h-4 w-4" />}
              Apply
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSelectedPairIds([]);
                setPairDialogOpen(true);
              }}
              disabled={isResponding}
            >
              <Link2 className="mr-2 h-4 w-4" />
              Save an item pair
            </Button>
          </div>
          {assistantReply && <p className="rounded-lg bg-muted p-2.5 text-sm text-muted-foreground">{assistantReply}</p>}
        </CardContent>
      </Card>

      <Dialog
        open={pairDialogOpen}
        onOpenChange={(open) => {
          setPairDialogOpen(open);
          if (!open) setSelectedPairIds([]);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Choose two pieces</DialogTitle>
            <DialogDescription>
              Select the exact relationship to remember. Other items in the outfit will not be paired.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
            {outfit.items.map((item) => {
              const checked = selectedPairIds.includes(item.id);
              const selectionFull = selectedPairIds.length === 2 && !checked;
              return (
                <label
                  key={item.id}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-xl border p-2.5 transition-colors',
                    checked && 'border-primary bg-primary/5',
                    selectionFull && 'cursor-not-allowed opacity-50',
                  )}
                >
                  <Checkbox
                    checked={checked}
                    disabled={isResponding || selectionFull}
                    onCheckedChange={(value) => {
                      setSelectedPairIds((current) =>
                        value === true
                          ? current.length < 2 ? [...current, item.id] : current
                          : current.filter((id) => id !== item.id),
                      );
                    }}
                    aria-label={`Pair ${item.name || item.type}`}
                  />
                  <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-muted">
                    {item.thumbnail_url || item.image_url ? (
                      <Image
                        src={item.thumbnail_url || item.image_url || ''}
                        alt={item.name || item.type}
                        fill
                        className="object-contain"
                        sizes="56px"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center">
                        <Shirt className="h-5 w-5 text-muted-foreground/50" />
                      </div>
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{item.name || item.type}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {[itemSlotLabel(item.type), item.brand, item.primary_color].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                </label>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">
            {selectedPairIds.length}/2 selected
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPairDialogOpen(false)} disabled={isResponding}>
              Cancel
            </Button>
            <Button onClick={saveSelectedPair} disabled={selectedPairIds.length !== 2 || isResponding}>
              {isResponding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
              Save pair
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Action buttons */}
      <div className="flex gap-3 justify-center">
        <Button variant="outline" size="lg" onClick={onTryAnother} className="gap-2" disabled={isResponding}>
          <RefreshCw className={cn('h-4 w-4', isResponding && 'animate-spin')} />
          Try Another
        </Button>
        <Button size="lg" onClick={onAccept} className="gap-2" disabled={isResponding}>
          <ThumbsUp className="h-4 w-4" />
          Love it
        </Button>
        <Button variant="ghost" size="lg" onClick={onReject} className="px-3" aria-label="Dismiss outfit" disabled={isResponding}>
          <ThumbsDown className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default function SuggestPage() {
  const { data: session } = useSession();
  const { data: weather, isLoading: weatherLoading } = useWeather();
  const { data: prefs } = usePreferences();
  const temperatureUnit: TempUnit = prefs?.temperature_unit === 'fahrenheit' ? 'fahrenheit' : 'celsius';
  const [selectedOccasion, setSelectedOccasion] = useState<string | null>(null);
  const [occasionInitialized, setOccasionInitialized] = useState(false);
  const [weatherOverride, setWeatherOverride] = useState<WeatherOverride | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [outfit, setOutfit] = useState<Outfit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isResponding, setIsResponding] = useState(false);
  const [strategy, setStrategy] = useState<'rules' | 'ai'>('rules');
  const { data: wardrobeData } = useItems({ is_archived: false }, 1, 100);

  useEffect(() => {
    if (prefs?.default_occasion && !occasionInitialized && !selectedOccasion) {
      setSelectedOccasion(prefs.default_occasion);
      setOccasionInitialized(true);
    }
  }, [prefs, occasionInitialized, selectedOccasion]);

  const handleGenerate = async () => {
    if (!selectedOccasion) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    setIsGenerating(true);
    setError(null);

    try {
      const request: SuggestRequest = {
        occasion: selectedOccasion,
        strategy,
      };

      if (weatherOverride) {
        request.weather_override = {
          temperature: weatherOverride.temperature,
          feels_like: weatherOverride.temperature,
          humidity: 50,
          precipitation_chance: weatherOverride.condition === 'rainy' ? 80 : weatherOverride.condition === 'cloudy' ? 30 : 10,
          condition: weatherOverride.condition,
        };
      }

      const result = await api.post<Outfit>('/outfits/suggest', request);
      setOutfit(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to generate outfit suggestion. Please try again.');
      }
      console.error('Suggestion error:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAccept = async () => {
    if (!outfit || isResponding) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    setIsResponding(true);
    try {
      await api.post(`/outfits/${outfit.id}/accept`);
      setOutfit(null);
      setSelectedOccasion(null);
      toast.success('Saved. Mark it worn from History after you wear it.');
    } catch (err) {
      console.error('Accept error:', err);
      toast.error('Could not save your response. Please try again.');
    } finally {
      setIsResponding(false);
    }
  };

  const handleTryAnother = async () => {
    if (!outfit || isResponding) return;
    setIsResponding(true);
    try {
      // Neutral signal: close this pending look without teaching the system that
      // every individual piece is disliked, then use a cached alternative.
      await api.post(`/outfits/${outfit.id}/skip`);
      setOutfit(null);
      await handleGenerate();
    } catch (err) {
      console.error('Try another error:', err);
      toast.error('Could not load another outfit. Please try again.');
    } finally {
      setIsResponding(false);
    }
  };

  const handleReject = async () => {
    if (!outfit || isResponding) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    setIsResponding(true);
    try {
      await api.post(`/outfits/${outfit.id}/reject`);
      setOutfit(null);
      await handleGenerate();
    } catch (err) {
      console.error('Reject error:', err);
      toast.error('Could not save your response. Please try again.');
    } finally {
      setIsResponding(false);
    }
  };

  const handleNewRequest = () => {
    setOutfit(null);
    setSelectedOccasion(null);
    setError(null);
  };

  const handleSwap = async (currentId: string, replacementId: string) => {
    if (!outfit || currentId === replacementId || isResponding) return;
    if (session?.accessToken) setAccessToken(session.accessToken as string);
    setIsResponding(true);
    try {
      const itemIds = outfit.items.map((item) => item.id === currentId ? replacementId : item.id);
      const updated = await api.patch<Outfit>(`/outfits/${outfit.id}`, { items: itemIds });
      setOutfit(updated);
    } catch (error) {
      console.error('Swap error:', error);
      toast.error('Could not swap that item.');
    } finally {
      setIsResponding(false);
    }
  };

  const handleRefine = async (message: string) => {
    if (!outfit || isResponding) return 'Please wait for the current change to finish.';
    if (session?.accessToken) setAccessToken(session.accessToken as string);
    setIsResponding(true);
    try {
      const result = await api.post<{ outfit: Outfit; reply: string }>(
        `/outfits/${outfit.id}/refine`,
        { message },
      );
      setOutfit(result.outfit);
      return result.reply;
    } catch (error) {
      console.error('Refine error:', error);
      toast.error('Could not apply that change.');
      return 'I could not apply that change. Try a specific garment, color, or brand.';
    } finally {
      setIsResponding(false);
    }
  };

  const handleKeepTogether = async (itemIds: string[]) => {
    if (!outfit || isResponding) return;
    if (session?.accessToken) setAccessToken(session.accessToken as string);
    setIsResponding(true);
    try {
      const result = await api.post<{ saved_pairs: number; message: string }>(
        `/outfits/${outfit.id}/keep-together`,
        { item_ids: itemIds },
      );
      toast.success(result.message);
    } catch (error) {
      console.error('Keep together error:', error);
      toast.error('Could not save this combination.');
    } finally {
      setIsResponding(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Page header with greeting */}
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{getGreeting()}</h1>
        <p className="text-muted-foreground">
          Let&apos;s find the perfect outfit for your day
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!outfit ? (
        <div className="space-y-6">
          {/* Weather context */}
          <WeatherCard weather={weather} isLoading={weatherLoading} temperatureUnit={temperatureUnit} />

          {isGenerating ? <OutfitGenerationProgress /> : (
          /* Main selection card */
          <Card>
            <CardContent className="p-6 space-y-6">
              {/* Occasion selection */}
              <div className="space-y-3">
                <h2 className="font-semibold">What&apos;s the occasion?</h2>
                <OccasionChips
                  selected={selectedOccasion}
                  onSelect={setSelectedOccasion}
                />
              </div>

              {/* Weather override (collapsible) */}
              <WeatherOverrideSection
                weather={weatherOverride}
                onChange={setWeatherOverride}
                temperatureUnit={temperatureUnit}
              />

              <div className="space-y-2">
                <h2 className="font-semibold">How should it build the outfit?</h2>
                <div className="grid grid-cols-2 gap-2 rounded-xl bg-muted p-1">
                  <button
                    type="button"
                    onClick={() => setStrategy('rules')}
                    className={cn('rounded-lg px-3 py-2 text-left transition-colors', strategy === 'rules' ? 'bg-background shadow-sm' : 'text-muted-foreground')}
                  >
                    <span className="block text-sm font-medium">Smart rules</span>
                    <span className="block text-xs text-muted-foreground">Instant · learned pairs · no LLM</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setStrategy('ai')}
                    className={cn('rounded-lg px-3 py-2 text-left transition-colors', strategy === 'ai' ? 'bg-background shadow-sm' : 'text-muted-foreground')}
                  >
                    <span className="block text-sm font-medium">AI stylist</span>
                    <span className="block text-xs text-muted-foreground">Creative · slower · uses text AI</span>
                  </button>
                </div>
              </div>

              {/* Generate button */}
              <div className="pt-2">
                <Button
                  size="lg"
                  className="w-full gap-2"
                  onClick={handleGenerate}
                  disabled={!selectedOccasion || isGenerating}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      Creating your look...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-5 w-5" />
                      Get Suggestion
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
          )}
        </div>
      ) : (
        <OutfitResult
          outfit={outfit}
          occasion={selectedOccasion || 'casual'}
          temperatureUnit={temperatureUnit}
          onAccept={handleAccept}
          onReject={handleReject}
          onTryAnother={handleTryAnother}
          onNewRequest={handleNewRequest}
          isResponding={isResponding}
          wardrobeItems={wardrobeData?.items || []}
          onSwap={handleSwap}
          onRefine={handleRefine}
          onKeepTogether={handleKeepTogether}
        />
      )}
    </div>
  );
}
