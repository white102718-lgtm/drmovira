import { describe, expect, it } from 'vitest';
import { ref } from 'vue';

import {
  areRouteQueriesEqual,
  createStringArrayRouteQueryField,
  mergeOwnedRouteQuery,
  readRouteQueryJson,
  readRouteQueryPositiveInteger,
  readRouteQueryText,
} from './use-route-list-query';

describe('route list query helpers', () => {
  it('reads the first scalar query value', () => {
    expect(readRouteQueryText(['keyword', 'ignored'])).toBe('keyword');
    expect(readRouteQueryText(null)).toBe('');
  });

  it('accepts only positive allowed pagination values', () => {
    expect(readRouteQueryPositiveInteger('3', 1)).toBe(3);
    expect(readRouteQueryPositiveInteger('0', 1)).toBe(1);
    expect(readRouteQueryPositiveInteger('20', 10, [10, 20, 50])).toBe(20);
    expect(readRouteQueryPositiveInteger('30', 10, [10, 20, 50])).toBe(10);
  });

  it('falls back when JSON is invalid or fails validation', () => {
    const fallback = { keyword: '' };
    const validate = (value: unknown): value is { keyword: string } =>
      Boolean(
        value &&
          typeof value === 'object' &&
          typeof Reflect.get(value, 'keyword') === 'string',
      );

    expect(
      readRouteQueryJson('{"keyword":"asset"}', fallback, validate),
    ).toEqual({ keyword: 'asset' });
    expect(readRouteQueryJson('{', fallback, validate)).toBe(fallback);
    expect(readRouteQueryJson('{"keyword":1}', fallback, validate)).toBe(
      fallback,
    );
  });

  it('restores dynamic filter JSON containing string arrays', () => {
    type Filters = Record<string, string | string[]>;
    const fallback: Filters = {};
    const validate = (value: unknown): value is Filters =>
      Boolean(
        value &&
          typeof value === 'object' &&
          Object.values(value).every(
            (item) =>
              typeof item === 'string' ||
              (Array.isArray(item) &&
                item.every((entry) => typeof entry === 'string')),
          ),
      );

    expect(
      readRouteQueryJson(
        '{"usageUsers":["u1","u2"],"status":"AVAILABLE"}',
        fallback,
        validate,
      ),
    ).toEqual({ status: 'AVAILABLE', usageUsers: ['u1', 'u2'] });
  });

  it('compares queries independently of key order', () => {
    expect(
      areRouteQueriesEqual(
        { q: 'asset', page: '2' },
        { page: '2', q: 'asset' },
      ),
    ).toBe(true);
    expect(areRouteQueriesEqual({ page: '2' }, { page: '3' })).toBe(false);
    expect(
      areRouteQueriesEqual({ type: ['a', 'b'] }, { type: ['a', 'b'] }),
    ).toBe(true);
  });

  it('updates owned keys and preserves unrelated deep-link parameters', () => {
    expect(
      mergeOwnedRouteQuery(
        { editId: '42', page: '3', source: 'my-assets' },
        { page: undefined, q: 'facebook' },
      ),
    ).toEqual({ editId: '42', q: 'facebook', source: 'my-assets' });
  });

  it('round-trips unique allowed string arrays', () => {
    const values = ref<string[]>([]);
    const field = createStringArrayRouteQueryField(values, {
      allowedValues: ['facebook', 'google'],
    });

    field.write(field.parse(['facebook', 'invalid', 'facebook', 'google']));

    expect(values.value).toEqual(['facebook', 'google']);
    expect(field.serialize(field.read())).toEqual(['facebook', 'google']);
  });
});
