import { describe, expect, it } from 'vitest'
import {
  configurationSecretError,
  configurationTextError,
} from '@/views/orbit/system/configuration/validation'

describe('配置字段Unicode和凭据边界', () => {
  it('NFC后按码点计数，合法emoji和组合字符不提前截断', () => {
    expect(configurationTextError('😀'.repeat(100), 100, true)).toBe('')
    expect(configurationTextError('e\u0301'.repeat(100), 100, true)).toBe('')
    expect(configurationTextError('😀'.repeat(101), 100, true)).toContain('100')
    expect(configurationTextError('  ', 100, true)).toBe('此项必填')
  })
  it('先拒控制符，不能通过trim去掉换行后放行', () => {
    for (const value of ['text\n', '\ttext', 'text\u2028', '\ud800']) {
      expect(configurationTextError(value, 100, true)).toBeTruthy()
    }
  })
  it('凭据不变换，空值和超限分别拒绝', () => {
    expect(configurationSecretError('  fixture  ')).toBe('')
    expect(configurationSecretError('😀'.repeat(8192))).toBe('')
    expect(configurationSecretError('😀'.repeat(8193))).toContain('8192')
    expect(configurationSecretError('')).toBeTruthy()
    expect(configurationSecretError('fixture\n')).toBeTruthy()
  })
})
