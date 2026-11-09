import type { Configuration, ConfigurationWrite } from './configuration'

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonical(item)]),
    )
  }
  return value
}

/** 同一次保存意图的网络重试复用键；仅内存保存不可导出的临时HMAC密钥及摘要。 */
export class ConfigurationSaveIntent {
  #signingKey?: Promise<CryptoKey>
  #fingerprint = ''
  #requestKey = ''
  #generation = 0

  async prepare(value: ConfigurationWrite, existing?: Configuration) {
    const generation = this.#generation
    this.#signingKey ??= crypto.subtle.generateKey({ name: 'HMAC', hash: 'SHA-256' }, false, [
      'sign',
    ])
    const signingKey = await this.#signingKey
    const data = new TextEncoder().encode(
      JSON.stringify(
        canonical({
          id: existing?.id ?? null,
          revision: existing?.revision ?? 0,
          value,
        }),
      ),
    )
    const signed = await crypto.subtle.sign('HMAC', signingKey, data)
    data.fill(0)
    if (generation !== this.#generation) throw new Error('保存操作已关闭，请重新操作')
    const fingerprint = Array.from(new Uint8Array(signed), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('')
    if (fingerprint !== this.#fingerprint) {
      this.#fingerprint = fingerprint
      this.#requestKey = crypto.randomUUID()
    }
    return this.#requestKey
  }

  reset() {
    this.#generation += 1
    this.#signingKey = undefined
    this.#fingerprint = ''
    this.#requestKey = ''
  }
}
