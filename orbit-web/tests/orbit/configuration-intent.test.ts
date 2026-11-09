import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ConfigurationSaveIntent } from '@/api/orbit/configuration-intent'
import type { Configuration, ConfigurationWrite } from '@/api/orbit/configuration'

beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => vi.unstubAllGlobals())
const value: ConfigurationWrite = {
  section: 'AI_GPT',
  name: '模型',
  enabled: false,
  settings: { model: 'fixture-model', timeoutSeconds: 60 },
  secrets: { apiKey: { operation: 'REPLACE', value: 'fixture-secret' } },
  reason: '人工保存',
}

it('同一意图重试复用键，字段顺序不影响，不保留可序列化凭据', async () => {
  const intent = new ConfigurationSaveIntent()
  const first = await intent.prepare(value)
  expect(
    await intent.prepare({ ...value, settings: { timeoutSeconds: 60, model: 'fixture-model' } }),
  ).toBe(first)
  expect(JSON.stringify(intent)).toBe('{}')
  expect(Object.keys(intent)).toEqual([])
})

it('内容、凭据、目标或版本改变均产生新键，重开明确结束旧意图', async () => {
  const intent = new ConfigurationSaveIntent()
  const first = await intent.prepare(value)
  const renamed = await intent.prepare({ ...value, name: '新模型' })
  expect(renamed).not.toBe(first)
  const rekeyed = await intent.prepare({
    ...value,
    secrets: { apiKey: { operation: 'REPLACE', value: 'new-secret' } },
  })
  expect(rekeyed).not.toBe(renamed)
  const revision1 = await intent.prepare(value, { id: 'fixture', revision: 1 } as Configuration)
  expect(await intent.prepare(value, { id: 'fixture', revision: 2 } as Configuration)).not.toBe(
    revision1,
  )
  intent.reset()
  expect(await intent.prepare(value)).not.toBe(first)
})
