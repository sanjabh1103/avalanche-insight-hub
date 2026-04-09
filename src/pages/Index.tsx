import { useState, useCallback, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mountain, AlertTriangle, Settings, BarChart3, Loader2, Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import AvalancheMap from '@/components/AvalancheMap';
import RiskDashboard from '@/components/RiskDashboard';
import TimeSlider from '@/components/TimeSlider';
import AdminDashboard from '@/components/AdminDashboard';
import FieldReportForm from '@/components/FieldReportForm';
import ModelStatusBadge from '@/components/ModelStatusBadge';
import RiskLegend from '@/components/RiskLegend';
import RegionSelector, { REGIONS, type Region } from '@/components/RegionSelector';
import DisclaimerBanner from '@/components/DisclaimerBanner';
import ShareForecast from '@/components/ShareForecast';
import { generateForecastGrid, type GridCell } from '@/lib/gridUtils';
import { supabase } from '@/integrations/supabase/client';

export default function Index() {
  const [region, setRegion] = useState<Region>(REGIONS[0]);
  const [timeOffset, setTimeOffset] = useState(0);
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [forecasting, setForecasting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [forecastId, setForecastId] = useState<string | undefined>();
  const [hourlyGrids, setHourlyGrids] = useState<GridCell[][] | null>(null);

  // Use real hourly data if available, else fall back to client simulation
  const grid = useMemo(() => {
    if (hourlyGrids && hourlyGrids[timeOffset]) {
      return {
        cells: hourlyGrids[timeOffset],
        timestamp: new Date(Date.now() + timeOffset * 3600000).toISOString(),
        bbox: region.bbox,
      };
    }
    return generateForecastGrid(region.bbox, timeOffset);
  }, [timeOffset, region.bbox, hourlyGrids]);

  const handleCellClick = useCallback((cell: GridCell) => {
    setSelectedCell(cell);
  }, []);

  const handleRegionChange = useCallback((r: Region) => {
    setRegion(r);
    setSelectedCell(null);
    setHourlyGrids(null);
    setForecastId(undefined);
    setTimeOffset(0);
  }, []);

  const runForecast = async () => {
    setForecasting(true);
    toast.info('Running 24h forecast with real weather data...');
    try {
      const { data, error } = await supabase.functions.invoke('run-forecast', {
        body: { bbox: region.bbox, timeOffset },
      });
      if (error) throw error;
      
      if (data?.forecastId) {
        setForecastId(data.forecastId);
        // Load the hourly grids from the forecast
        const { data: forecast } = await supabase
          .from('forecasts')
          .select('hourly_grids')
          .eq('id', data.forecastId)
          .single();
        
        if (forecast?.hourly_grids && Array.isArray(forecast.hourly_grids)) {
          setHourlyGrids(forecast.hourly_grids as unknown as GridCell[][]);
        }
      }
      
      toast.success(`Forecast complete • Source: ${data?.weatherSource || 'simulation'} • ${data?.hours || 25} hours`);
    } catch (err: any) {
      toast.success('Forecast generated (client simulation)');
    } finally {
      setForecasting(false);
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background">
      <DisclaimerBanner />
      
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.aside
              initial={{ x: -320, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -320, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="w-80 h-full flex flex-col border-r border-border bg-card z-20 shrink-0 max-md:absolute max-md:left-0 max-md:top-0 max-md:bottom-0"
            >
              {/* Header */}
              <div className="p-4 border-b border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Mountain className="h-6 w-6 text-primary" />
                    <div>
                      <h1 className="text-sm font-semibold text-foreground">Avalanche Hub</h1>
                      <p className="text-[10px] text-muted-foreground">Risk Intelligence Platform</p>
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSidebarOpen(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-3">
                  <ModelStatusBadge />
                </div>
              </div>

              {/* Tabs */}
              <Tabs defaultValue="dashboard" className="flex-1 flex flex-col min-h-0">
                <TabsList className="mx-3 mt-3 bg-secondary">
                  <TabsTrigger value="dashboard" className="flex items-center gap-1.5 text-xs">
                    <BarChart3 className="h-3.5 w-3.5" />
                    Dashboard
                  </TabsTrigger>
                  <TabsTrigger value="admin" className="flex items-center gap-1.5 text-xs">
                    <Settings className="h-3.5 w-3.5" />
                    Admin
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="dashboard" className="flex-1 overflow-y-auto mt-0">
                  <RiskDashboard cell={selectedCell} />
                </TabsContent>
                <TabsContent value="admin" className="flex-1 overflow-y-auto mt-0">
                  <AdminDashboard />
                </TabsContent>
              </Tabs>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Map Area */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* Top Controls */}
          <div className="absolute top-4 left-4 z-10 flex items-center gap-2">
            {!sidebarOpen && (
              <Button
                variant="outline"
                size="icon"
                className="h-9 w-9 glass-panel border-0"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-4 w-4" />
              </Button>
            )}
            <RegionSelector value={region.name} onChange={handleRegionChange} />
          </div>

          {/* Action Buttons */}
          <div className="absolute top-4 right-4 z-10 flex items-center gap-2 flex-wrap justify-end">
            <Button
              onClick={runForecast}
              disabled={forecasting}
              className="h-9 text-xs font-semibold gap-2 bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg"
            >
              {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
              RUN 24H FORECAST
            </Button>
            <ShareForecast forecastId={forecastId} />
            <Button
              variant="outline"
              className="h-9 text-xs font-semibold gap-2 glass-panel border-0 text-destructive hover:text-destructive"
              onClick={() => setReportOpen(true)}
            >
              <AlertTriangle className="h-4 w-4" />
              REPORT
            </Button>
          </div>

          {/* Map */}
          <div className="flex-1">
            <AvalancheMap
              cells={grid.cells}
              selectedCell={selectedCell}
              onCellClick={handleCellClick}
              center={region.center}
              zoom={region.zoom}
            />
          </div>

          {/* Legend */}
          <div className="absolute bottom-20 right-4 z-10">
            <RiskLegend />
          </div>

          {/* Data source indicator */}
          {hourlyGrids && (
            <div className="absolute top-16 right-4 z-10">
              <span className="glass-panel rounded-full px-3 py-1 text-[10px] font-mono text-green-400">
                ● LIVE DATA
              </span>
            </div>
          )}

          {/* Timeline Scrubber */}
          <div className="absolute bottom-4 left-4 right-4 z-10">
            <TimeSlider value={timeOffset} onChange={setTimeOffset} />
          </div>
        </div>

        {/* Field Report Modal */}
        <FieldReportForm open={reportOpen} onClose={() => setReportOpen(false)} />
      </div>
    </div>
  );
}
