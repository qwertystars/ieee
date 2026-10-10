const CROCK32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
let lastTs = 0
let lastRand = new Uint8Array(10)

function encode32(value: bigint, length: number): string {
  let result = ''
  for (let index = 0; index < length; index++) {
    result = CROCK32[Number(value & 31n)] + result
    value >>= 5n
  }
  return result
}

export function ulid(): string {
  let timestamp = Math.max(Date.now(), lastTs)
  const random = timestamp === lastTs ? new Uint8Array(lastRand) : crypto.getRandomValues(new Uint8Array(10))
  if (timestamp === lastTs) {
    let overflow = true
    for (let index = random.length - 1; index >= 0; index--) {
      if (random[index] === 255) random[index] = 0
      else { random[index] += 1; overflow = false; break }
    }
    if (overflow) {
      timestamp += 1
      random.fill(0)
    }
  }
  lastTs = timestamp
  lastRand = random
  let value = 0n
  for (const byte of random) value = (value << 8n) | BigInt(byte)
  return encode32(BigInt(timestamp), 10) + encode32(value, 16)
}
