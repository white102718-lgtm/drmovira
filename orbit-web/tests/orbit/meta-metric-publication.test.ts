import { describe, it, expect } from 'vitest'
import {
  parsePublicationOptions,
  parsePublicationResult,
} from '@/api/orbit/meta-metric-publication'
describe('真实指标口径发布协议', () => {
  it('保留原配置字段并明确未配置状态', () => {
    const value = {
      csrf_token: 'csrf',
      configured: false,
      api_version: null,
      adapter_version: 'META_INSIGHTS_V24_EXPLICIT_V1',
      attribution_windows: ['1d_click'],
      action_report_times: ['conversion'],
      configurations: [],
      connections: [],
    }
    expect(parsePublicationOptions(value).configured).toBe(false)
    expect(() => parsePublicationOptions({ ...value, configured: 'true' })).toThrow()
  })
  it('拒绝伪造发布成功与不完整回执', () => {
    expect(() => parsePublicationResult({ verified: true })).toThrow()
    expect(
      parsePublicationResult({
        id: '00000000-0000-4000-8000-000000000001',
        version: 'release',
        revision: 1,
        adapter_version: 'META_INSIGHTS_V24_EXPLICIT_V1',
      }).revision,
    ).toBe(1)
  })
})
