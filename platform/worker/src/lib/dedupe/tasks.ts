// T58: Help request dedupe (phone + geo + time window + embedding similarity).

export interface DedupeKey {
  contactPhone: string | null;
  geo: string | null;
  category: string;
  windowMs: number;
}

export function dedupeKey(input: DedupeKey): string {
  const phone = input.contactPhone ?? 'none';
  const geoHash = input.geo ? simpleGeoHash(input.geo) : 'none';
  return `${phone}|${geoHash}|${input.category}`;
}

export function simpleGeoHash(geo: string): string {
  try {
    const parsed = JSON.parse(geo) as { coordinates: [number, number] };
    const [lng, lat] = parsed.coordinates;
    return `${lng.toFixed(3)},${lat.toFixed(3)}`;
  } catch {
    return 'unknown';
  }
}

export function jaroWinkler(s1: string, s2: string): number {
  const a = s1.toLowerCase().trim();
  const b = s2.toLowerCase().trim();
  if (a === b) return 1;
  if (a.length === 0 || b.length === 0) return 0;

  const matchDistance = Math.floor(Math.max(a.length, b.length) / 2) - 1;
  const aMatches = new Array<boolean>(a.length).fill(false);
  const bMatches = new Array<boolean>(b.length).fill(false);
  let matches = 0;

  for (let i = 0; i < a.length; i++) {
    const start = Math.max(0, i - matchDistance);
    const end = Math.min(i + matchDistance + 1, b.length);
    for (let j = start; j < end; j++) {
      if (!bMatches[j] && a[i] === b[j]) {
        aMatches[i] = true;
        bMatches[j] = true;
        matches++;
        break;
      }
    }
  }

  if (matches === 0) return 0;

  let transpositions = 0;
  let k = 0;
  for (let i = 0; i < a.length; i++) {
    if (aMatches[i]) {
      while (!bMatches[k]) k++;
      if (a[i] !== b[k]) transpositions++;
      k++;
    }
  }
  transpositions /= 2;

  const jaro = (matches / a.length + matches / b.length + (matches - transpositions) / matches) / 3;
  let prefix = 0;
  for (let i = 0; i < Math.min(4, a.length, b.length); i++) {
    if (a[i] !== b[i]) break;
    prefix++;
  }
  return jaro + prefix * 0.1 * (1 - jaro);
}
