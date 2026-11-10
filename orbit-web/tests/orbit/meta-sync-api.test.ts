import { describe, expect, it } from 'vitest'
import { parseMetaSyncSettings, parseMetaSyncStatus } from '@/api/orbit/meta-sync'
const id = '10000000-0000-4000-8000-000000000001'
describe('Meta采集状态合同', () => {
  it('未设置保持关闭及未知口径', () => {
    expect(
      parseMetaSyncSettings({
        profile_id: null,
        adapter_version: null,
        scheduler_enabled: false,
        revision: 0,
        csrf_token: 'csrf',
        choices: [],
      }).scheduler_enabled,
    ).toBe(false)
  })
  it('拒绝把未设置解释为已开启', () => {
    expect(() =>
      parseMetaSyncSettings({
        profile_id: null,
        adapter_version: null,
        scheduler_enabled: true,
        revision: 0,
        csrf_token: 'csrf',
        choices: [],
      }),
    ).toThrow()
  })
  it('状态完整性和最近成功时间独立于最新失败', () => {
    const value = {
      items: [
        { account_id: id, account_name: '隔离账户', latest_job: null, last_published_at: null },
      ],
      next_cursor: null,
      scope_version: 1,
      data_as_of: '2026-11-10T00:00:00.000000Z',
    }
    expect(parseMetaSyncStatus(value).items[0].latest_job).toBeNull()
    expect(() => parseMetaSyncStatus({ ...value, items: Array(51).fill(value.items[0]) })).toThrow()
  })
})
