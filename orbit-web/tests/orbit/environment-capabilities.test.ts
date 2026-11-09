import { describe, it, expect } from 'vitest'
import { parseCapabilityPage } from '@/api/orbit/environment-capabilities'
describe('动作能力响应', () => {
  it('保留真实空列表不制造已验证动作', () =>
    expect(
      parseCapabilityPage({
        items: [],
        next_cursor: null,
        data_as_of: '2026-11-10T00:00:00Z',
        scope_version: 1,
      }).items,
    ).toEqual([]))
  it('拒绝额外字段', () =>
    expect(() =>
      parseCapabilityPage({
        items: [],
        next_cursor: null,
        data_as_of: '2026-11-10T00:00:00Z',
        scope_version: 1,
        verified: true,
      }),
    ).toThrow())
  it('拒绝无证据的已验证动作', () =>
    expect(() =>
      parseCapabilityPage({
        items: [{ id: 'a' }],
        next_cursor: null,
        data_as_of: '2026-11-10T00:00:00Z',
        scope_version: 1,
      }),
    ).toThrow())
})
