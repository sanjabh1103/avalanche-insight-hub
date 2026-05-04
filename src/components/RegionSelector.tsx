import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MapPin } from 'lucide-react';
import regionCatalog from '../../config/regions.json';

export interface Region {
  name: string;
  bbox: [number, number, number, number];
  center: [number, number];
  zoom: number;
  timezone_name?: string;
}

export const REGIONS: Region[] = regionCatalog as Region[];

interface Props {
  value: string;
  onChange: (region: Region) => void;
}

export default function RegionSelector({ value, onChange }: Props) {
  return (
    <Select value={value} onValueChange={(name) => {
      const region = REGIONS.find(r => r.name === name);
      if (region) onChange(region);
    }}>
      <SelectTrigger className="h-11 w-full min-w-0 text-xs glass-panel border-0 gap-1.5 text-foreground sm:w-[15rem] xl:w-56">
        <MapPin className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
        <SelectValue placeholder="Select Region" />
      </SelectTrigger>
      <SelectContent className="bg-card border-border">
        {REGIONS.map(r => (
          <SelectItem key={r.name} value={r.name} className="text-xs">
            {r.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
