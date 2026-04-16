import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MapPin } from 'lucide-react';

export interface Region {
  name: string;
  bbox: [number, number, number, number];
  center: [number, number];
  zoom: number;
}

export const REGIONS: Region[] = [
  { name: 'Colorado Rockies', bbox: [38.5, -107.5, 40.5, -105.5], center: [39.5, -106.5], zoom: 9 },
  { name: 'Swiss Alps', bbox: [46.0, 7.0, 47.5, 9.5], center: [46.75, 8.25], zoom: 9 },
  { name: 'French Alps', bbox: [44.5, 5.5, 46.5, 7.5], center: [45.5, 6.5], zoom: 9 },
  { name: 'Himalayas (Nepal)', bbox: [27.0, 85.0, 29.0, 87.5], center: [28.0, 86.25], zoom: 8 },
  { name: 'Andes (Patagonia)', bbox: [-42.0, -72.0, -40.0, -70.0], center: [-41.0, -71.0], zoom: 9 },
  { name: 'Cascades (WA)', bbox: [46.5, -122.5, 48.5, -120.5], center: [47.5, -121.5], zoom: 9 },
  { name: 'Scandinavia (Norway)', bbox: [60.0, 6.0, 62.0, 8.0], center: [61.0, 7.0], zoom: 9 },
  { name: 'Japanese Alps', bbox: [35.5, 137.0, 37.0, 139.0], center: [36.25, 138.0], zoom: 9 },
];

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
      <SelectTrigger className="h-10 w-56 text-xs glass-panel border-0 gap-1.5 text-foreground">
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
