/** 流式SHA-256；最多保留一个1MiB读取块，避免500MiB视频整体进入ArrayBuffer。 */
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])
const rotate = (value: number, shift: number) => (value >>> shift) | (value << (32 - shift))

export class MaterialSha256 {
  private state = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ])
  private block = new Uint8Array(64)
  private words = new Uint32Array(64)
  private count = 0
  private used = 0
  private finished = false
  update(data: Uint8Array) {
    if (this.finished) throw new Error('摘要已经结束')
    this.count += data.length
    let offset = 0
    while (offset < data.length) {
      const length = Math.min(64 - this.used, data.length - offset)
      this.block.set(data.subarray(offset, offset + length), this.used)
      this.used += length
      offset += length
      if (this.used === 64) {
        this.compress()
        this.used = 0
      }
    }
    return this
  }
  private compress() {
    const words = this.words
    const view = new DataView(this.block.buffer)
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(i * 4)
    for (let i = 16; i < 64; i++) {
      const x = words[i - 15],
        y = words[i - 2]
      words[i] =
        words[i - 16] +
        (rotate(x, 7) ^ rotate(x, 18) ^ (x >>> 3)) +
        words[i - 7] +
        (rotate(y, 17) ^ rotate(y, 19) ^ (y >>> 10))
    }
    let [a, b, c, d, e, f, g, h] = this.state
    for (let i = 0; i < 64; i++) {
      const t1 =
        (h +
          (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) +
          ((e & f) ^ (~e & g)) +
          K[i] +
          words[i]) >>>
        0
      const t2 =
        ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0
      h = g
      g = f
      f = e
      e = (d + t1) >>> 0
      d = c
      c = b
      b = a
      a = (t1 + t2) >>> 0
    }
    for (const [i, value] of [a, b, c, d, e, f, g, h].entries()) this.state[i] += value
  }
  digest() {
    if (this.finished) throw new Error('摘要已经结束')
    const bits = this.count * 8
    this.update(new Uint8Array([0x80]))
    while (this.used !== 56) this.update(new Uint8Array([0]))
    const ending = new Uint8Array(8)
    const view = new DataView(ending.buffer)
    view.setUint32(0, Math.floor(bits / 0x100000000))
    view.setUint32(4, bits >>> 0)
    this.update(ending)
    this.finished = true
    return Array.from(this.state, (n) => n.toString(16).padStart(8, '0')).join('')
  }
}

export async function hashMaterialFile(file: Blob, signal?: AbortSignal) {
  const hash = new MaterialSha256()
  for (let offset = 0; offset < file.size; offset += 1024 * 1024) {
    signal?.throwIfAborted()
    hash.update(new Uint8Array(await file.slice(offset, offset + 1024 * 1024).arrayBuffer()))
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
  signal?.throwIfAborted()
  return hash.digest()
}
