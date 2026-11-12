/**
 * RFC 4180-style CSV serialization helper.
 *
 * Records are separated by CRLF (`\r\n`). Fields containing comma, double-quote,
 * CR, or LF are wrapped in double quotes and internal double quotes are escaped
 * by doubling them (`""`). Null/undefined values are emitted as empty fields.
 */

export const CSV_RECORD_SEPARATOR = '\r\n';

export function csvEscape(value: string | number | null | undefined): string {
  const str = value == null ? '' : String(value);
  const needsQuoting = str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r');
  if (needsQuoting) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function buildCsvTable(headers: string[], rows: Array<Array<string | number | null | undefined>>): string {
  const lines = [headers.map(csvEscape).join(','), ...rows.map((r) => r.map(csvEscape).join(','))];
  return lines.join(CSV_RECORD_SEPARATOR);
}
