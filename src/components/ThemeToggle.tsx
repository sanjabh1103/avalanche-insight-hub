import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { Sun, Moon, Laptop } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="outline" size="sm" className="h-9 w-9 glass-panel border-0 p-0">
        <span className="sr-only">Toggle theme</span>
      </Button>
    );
  }

  const cycleTheme = () => {
    if (resolvedTheme === 'dark') {
      setTheme('light');
    } else {
      setTheme('dark');
    }
  };

  const Icon = resolvedTheme === 'dark' ? Moon : resolvedTheme === 'light' ? Sun : Laptop;

  return (
    <Button
      variant="outline"
      size="sm"
      className="h-9 w-9 glass-panel border-0 p-0"
      onClick={cycleTheme}
      title={`Theme: ${resolvedTheme || theme} (click to toggle)`}
    >
      <Icon className="h-4 w-4" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
