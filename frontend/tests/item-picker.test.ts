import { describe, it, expect } from 'vitest';
import { groupItemsByType } from '@/components/shared/item-picker';
import type { Item } from '@/lib/types';

function makeItem(overrides: Partial<Item> & { type: string; id: string }): Item {
  return {
    user_id: 'u1',
    name: null,
    favorite: false,
    image_path: 'test.jpg',
    tags: { colors: [], style: [], season: [] },
    colors: [],
    status: 'ready',
    ai_processed: true,
    ai_catalog_cutout: false,
    tagging_status: 'tagged',
    wear_count: 0,
    suggestion_count: 0,
    acceptance_count: 0,
    wears_since_wash: 0,
    needs_wash: false,
    effective_wash_interval: null,
    additional_images: [],
    is_archived: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as Item;
}

describe('groupItemsByType', () => {
  it('groups items into sections keyed by exact type', () => {
    const items = [
      makeItem({ id: '1', type: 'shirt' }),
      makeItem({ id: '2', type: 'pants' }),
      makeItem({ id: '3', type: 'shirt' }),
    ];

    const groups = groupItemsByType(items);
    const shirtGroup = groups.find((g) => g.type === 'shirt');
    const pantsGroup = groups.find((g) => g.type === 'pants');

    expect(shirtGroup?.items).toHaveLength(2);
    expect(pantsGroup?.items).toHaveLength(1);
  });

  it('orders sections in outfit-building order (tops before bottoms before shoes)', () => {
    const items = [
      makeItem({ id: '1', type: 'sneakers' }),
      makeItem({ id: '2', type: 'pants' }),
      makeItem({ id: '3', type: 't-shirt' }),
      makeItem({ id: '4', type: 'jacket' }),
    ];

    const groups = groupItemsByType(items);
    const order = groups.map((g) => g.type);

    expect(order.indexOf('t-shirt')).toBeLessThan(order.indexOf('jacket'));
    expect(order.indexOf('jacket')).toBeLessThan(order.indexOf('pants'));
    expect(order.indexOf('pants')).toBeLessThan(order.indexOf('sneakers'));
  });

  it('uses a friendly label from CLOTHING_TYPES', () => {
    const groups = groupItemsByType([makeItem({ id: '1', type: 't-shirt' })]);
    expect(groups[0].label).toBe('T-Shirt');
  });

  it('falls back to a capitalized label for unknown types, sorted last', () => {
    const groups = groupItemsByType([
      makeItem({ id: '1', type: 'shirt' }),
      makeItem({ id: '2', type: 'mystery-item' }),
    ]);
    const mystery = groups.find((g) => g.type === 'mystery-item');
    expect(mystery?.label).toBe('Mystery-item');
    expect(groups[groups.length - 1].type).toBe('mystery-item');
  });

  it('returns no groups for an empty item list', () => {
    expect(groupItemsByType([])).toEqual([]);
  });
});
