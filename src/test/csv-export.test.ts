import { describe, expect, it } from 'vitest';
import { CSV_RECORD_SEPARATOR, buildCsvTable, csvEscape } from '@/lib/csvExport';

describe('csvExport', () => {
  it('does not quote simple fields', () => {
    expect(csvEscape('hello')).toBe('hello');
    expect(csvEscape(42)).toBe('42');
    expect(csvEscape(0)).toBe('0');
  });

  it('quotes fields containing commas', () => {
    expect(csvEscape('Persistent, Deep Slab')).toBe('"Persistent, Deep Slab"');
  });

  it('quotes fields containing double quotes and doubles them', () => {
    expect(csvEscape('He said "avalanche"')).toBe('"He said ""avalanche"""');
  });

  it('quotes fields containing newlines', () => {
    expect(csvEscape('line1\nline2')).toBe('"line1\nline2"');
  });

  it('quotes fields containing carriage returns', () => {
    expect(csvEscape('line1\rline2')).toBe('"line1\rline2"');
  });

  it('quotes fields containing CRLF', () => {
    expect(csvEscape('line1\r\nline2')).toBe('"line1\r\nline2"');
  });

  it('renders null and undefined as empty fields', () => {
    expect(csvEscape(null)).toBe('');
    expect(csvEscape(undefined)).toBe('');
  });

  it('builds a table with CRLF record separators', () => {
    const table = buildCsvTable(['a', 'b'], [
      [1, 2],
      [3, 4],
    ]);
    expect(table).toBe(`a,b${CSV_RECORD_SEPARATOR}1,2${CSV_RECORD_SEPARATOR}3,4`);
  });

  it('produces equal column counts for every row', () => {
    const headers = ['h1', 'h2', 'h3'];
    const rows = [
      ['a', null, 'c'],
      ['x', 'y', 'z'],
    ];
    const table = buildCsvTable(headers, rows);
    const lines = table.split(CSV_RECORD_SEPARATOR);
    expect(lines).toHaveLength(3);
    for (const line of lines) {
      expect(line.split(',')).toHaveLength(3);
    }
  });
});
