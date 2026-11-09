import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { MaterialSha256 } from '../../src/api/orbit/material-hash'

describe('素材有界SHA256', () => {
  for (const size of [0, 1, 55, 56, 63, 64, 65, 511, 1048576 + 37]) {
    it(`跨块摘要与独立Node实现一致：${size}字节`, () => {
      const data = Uint8Array.from({ length: size }, (_, i) => i % 251)
      const hash = new MaterialSha256()
      for (let offset = 0; offset < data.length; offset += 71)
        hash.update(data.subarray(offset, offset + 71))
      expect(hash.digest()).toBe(createHash('sha256').update(data).digest('hex'))
      expect(() => hash.digest()).toThrow()
    })
  }
  it('标准abc向量', () => {
    expect(new MaterialSha256().update(new TextEncoder().encode('abc')).digest()).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
  })
})
