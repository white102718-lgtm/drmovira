import { describe, expect, it } from 'vitest';

import { parseAdAccountSearchIds } from './ad-account-search';

describe('parseAdAccountSearchIds', () => {
  it('splits pasted IDs by spaces and line breaks', () => {
    expect(parseAdAccountSearchIds('act_10001 act_10002\nact_10003')).toEqual([
      'act_10001',
      'act_10002',
      'act_10003',
    ]);
  });

  it('accepts existing comma and semicolon separators', () => {
    expect(parseAdAccountSearchIds('act_10001,act_10002；act_10003')).toEqual([
      'act_10001',
      'act_10002',
      'act_10003',
    ]);
  });

  it('removes blank and duplicate IDs', () => {
    expect(parseAdAccountSearchIds('  act_10001\n\nact_10001  ')).toEqual([
      'act_10001',
    ]);
  });

  it('returns undefined when no ID was entered', () => {
    expect(parseAdAccountSearchIds(' \n ')).toBeUndefined();
  });
});
