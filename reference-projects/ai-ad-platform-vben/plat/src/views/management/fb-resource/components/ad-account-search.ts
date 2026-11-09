/**
 * Normalizes a pasted advertising-account ID query into the repeated `id`
 * parameters expected by the resource API.
 */
export function parseAdAccountSearchIds(value?: string): string[] | undefined {
  const ids = [
    ...new Set(
      (value ?? '')
        .trim()
        .split(/[\s,;，；]+/)
        .filter(Boolean),
    ),
  ];

  return ids.length > 0 ? ids : undefined;
}
