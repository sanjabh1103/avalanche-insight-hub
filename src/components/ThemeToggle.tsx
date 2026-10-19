import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { Sun, Moon, Laptop } from 'lucide-react';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

export default function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="outline" size="sm" className={cn('h-10 px-3 glass-panel border-0 gap-2 rounded-2xl', className)}>
        <span className="sr-only">Toggle theme</span>
      </Button>
    );
  }

  const cycleTheme = () => {
    const nextTheme = resolvedTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark', nextTheme === 'dark');
    window.localStorage.setItem('avalanche-insight-theme', nextTheme);
    setTheme(nextTheme);
  };

  const Icon = resolvedTheme === 'dark' ? Moon : resolvedTheme === 'light' ? Sun : Laptop;

  return (
    <Button
      variant="outline"
      size="sm"
      className={cn('h-10 px-3 glass-panel border-0 gap-2 font-semibold whitespace-nowrap bg-card/80 rounded-2xl', className)}
      onClick={cycleTheme}
      title={`Theme: ${resolvedTheme || theme} (click to toggle)`}
      aria-label={`Toggle theme. Current theme: ${resolvedTheme || theme}`}
    >
      <Icon className="h-4 w-4" />
      <span className="text-xs uppercase tracking-[0.22em]">Theme</span>
      <span className="hidden sm:inline text-[10px] font-mono text-muted-foreground">
        {resolvedTheme === 'dark' ? 'Dark' : 'Light'}
      </span>
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
