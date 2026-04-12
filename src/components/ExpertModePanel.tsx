import { motion, AnimatePresence } from 'framer-motion';
import { X, Bell, Layers, Map as MapIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import HydrographChart from '@/components/HydrographChart';
import { supabase } from '@/integrations/supabase/client';
import type { GridCell } from '@/lib/gridUtils';

interface Props {
  open: boolean;
  onClose: () => void;
  showHeatmap: boolean;
  onToggleHeatmap: (v: boolean) => void;
  showRoads: boolean;
  onToggleRoads: (v: boolean) => void;
  showInfra: boolean;
  onToggleInfra: (v: boolean) => void;
  showVectorPolygons: boolean;
  onToggleVectorPolygons: (v: boolean) => void;
  hourlyGrids: GridCell[][] | null;
  selectedCell: GridCell | null;
  regionBbox: [number, number, number, number];
}

export default function ExpertModePanel({
  open, onClose,
  showHeatmap, onToggleHeatmap,
  showRoads, onToggleRoads,
  showInfra, onToggleInfra,
  showVectorPolygons, onToggleVectorPolygons,
  hourlyGrids, selectedCell, regionBbox,
}: Props) {

  const subscribeAlerts = async () => {
    try {
      if (!('Notification' in window) || !('serviceWorker' in navigator)) {
        toast.error('Push notifications not supported in this browser');
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        toast.error('Notification permission denied');
        return;
      }
      // Store a stub subscription
      await supabase.from('user_alerts').insert({
        endpoint: `stub-${Date.now()}`,
        p256dh: 'stub',
        auth_key: 'stub',
        region_bbox: regionBbox as unknown as number[],
      });
      toast.success('Alert subscription saved for this region');
    } catch {
      toast.error('Failed to subscribe');
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="w-80 h-full flex flex-col border-l border-border bg-card z-30 shrink-0 absolute md:relative right-0 top-0 bottom-0 shadow-xl overflow-y-auto"
        >
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">Expert Mode</span>
            </div>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="p-4 space-y-4">
            {/* Impact Overlays */}
            <Card className="border-0 bg-secondary/50">
              <CardHeader className="p-3 pb-1">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <MapIcon className="h-3 w-3" /> Impact Overlays
                </CardTitle>
              </CardHeader>
              <CardContent className="p-3 pt-2 space-y-3">
                <ToggleRow label="Roads & Highways" tooltip="Show primary/secondary roads from OpenStreetMap" checked={showRoads} onToggle={onToggleRoads} />
                <ToggleRow label="Villages & Ski Lifts" tooltip="Show villages, towns, and aerial lifts" checked={showInfra} onToggle={onToggleInfra} />
                <ToggleRow label="Activity Heatmap" tooltip="Historical avalanche event density" checked={showHeatmap} onToggle={onToggleHeatmap} />
                <ToggleRow label="Vector Polygons" tooltip="Smooth high-risk cells into slope-path polygons (Turf.js)" checked={showVectorPolygons} onToggle={onToggleVectorPolygons} />
              </CardContent>
            </Card>

            {/* Hydrograph */}
            <HydrographChart hourlyGrids={hourlyGrids} selectedCell={selectedCell} />

            {/* Alerts */}
            <Card className="border-0 bg-secondary/50">
              <CardContent className="p-3">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full gap-2 text-xs"
                  onClick={subscribeAlerts}
                  aria-label="Subscribe to alerts for this region"
                >
                  <Bell className="h-3.5 w-3.5" />
                  Subscribe to Alerts
                </Button>
              </CardContent>
            </Card>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function ToggleRow({ label, tooltip, checked, onToggle }: { label: string; tooltip: string; checked: boolean; onToggle: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <Tooltip>
        <TooltipTrigger asChild>
          <Label className="text-xs cursor-pointer">{label}</Label>
        </TooltipTrigger>
        <TooltipContent side="left" className="text-xs">{tooltip}</TooltipContent>
      </Tooltip>
      <Switch checked={checked} onCheckedChange={onToggle} aria-label={label} />
    </div>
  );
}
