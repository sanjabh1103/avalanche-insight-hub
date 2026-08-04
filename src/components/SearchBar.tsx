import { useState, useEffect, useCallback } from 'react';

interface Props {
  onSearch: (query: string) => void;
  placeholder?: string;
}

export default function SearchBar({ onSearch, placeholder = 'Search nodes...' }: Props) {
  const [query, setQuery] = useState('');

  const debouncedSearch = useCallback(onSearch, [onSearch]);

  useEffect(() => {
    const timer = setTimeout(() => debouncedSearch(query), 200);
    return () => clearTimeout(timer);
  }, [query, debouncedSearch]);

  return (
    <input
      type="text"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      placeholder={placeholder}
      style={{
        width: '100%',
        padding: '0.5rem 0.75rem',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '0.375rem',
        color: 'var(--text)',
        fontSize: '0.9rem',
        outline: 'none',
      }}
    />
  );
}
