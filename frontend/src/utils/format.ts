const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

export function formatCents(cents: number): string {
  return usd.format(cents / 100);
}

export function formatFee(cents: number): string {
  return cents === 0 ? 'No fee' : formatCents(cents);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export function parseServerDate(d: string): Date {
  if (d.includes('T') && !/(?:[Zz]|[+-]\d\d:?\d\d)$/.test(d)) {
    return new Date(`${d}Z`);
  }
  return new Date(d);
}

const DATE_TIME: Intl.DateTimeFormatOptions = {
  year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
};

export function formatDateTime(value: string | null, timeZone?: string): string {
  if (!value) return 'Not recorded';
  return parseServerDate(value).toLocaleString('en-US', { ...DATE_TIME, timeZone });
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function formatShortDate(d: string | null): string {
  if (!d) return '--';
  return parseServerDate(d).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}

export function formatCourtDate(value: string | null): string {
  if (!value) return 'Not established';
  return new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  });
}
