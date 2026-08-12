export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })
}

export function formatRange(range: [number, number] | null | undefined, digits = 3): string {
  if (!range) return '—'
  return `${formatNumber(range[0], digits)} – ${formatNumber(range[1], digits)}`
}
