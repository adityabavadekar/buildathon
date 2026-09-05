export function formatINR(
  paise: number,
  options?: { maximumFractionDigits?: number },
): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: options?.maximumFractionDigits ?? 0,
  }).format(rupees)
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function humanizeToken(value: string): string {
  return value
    .replace(/[._]/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function formatCustomerName(customerId: string): string {
  const raw = customerId.replace(/^cust_/i, '')
  const parts = raw.split('_').filter((part) => part.length > 0)
  if (parts.length === 0) return customerId
  return parts
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

/** Replace every bare "<integer> paise" occurrence in free text with formatted INR. */
export function inlinePaiseToINR(text: string): string {
  return text.replace(/(\d+)\s*paise/g, (_match, digits: string) =>
    formatINR(Number(digits), { maximumFractionDigits: 2 }),
  )
}
