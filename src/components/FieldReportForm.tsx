import { useState, useEffect, useCallback } from 'react';
import { CircleMarker, MapContainer, Rectangle, TileLayer, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CalendarClock, Loader2, LocateFixed, MapPin, Send, WifiOff } from 'lucide-react';
import { toast } from 'sonner';
import type { AvalancheEvent } from '@/lib/avalancheEvents';
import { buildOptimisticFieldReportEvent } from '@/lib/avalancheEvents';
import {
  enqueueFieldReport,
  flushQueuedFieldReports,
  type QueuedFieldReport,
} from '@/lib/offlineFieldReports';
import { submitQueuedFieldReport } from '@/lib/fieldReportSync';
import { supabase } from '@/integrations/supabase/client';

function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  return online;
}

function toDateTimeLocalValue(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function toObservedAtIso(value: string): string {
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : new Date().toISOString();
}

function buildClientReportId() {
  const uuid = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `field-${uuid}`;
}

function LocationPickerInteraction({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(event) {
      onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

function LocationPickerMap({
  center,
  markerPosition,
  regionBbox,
  onPick,
}: {
  center: [number, number];
  markerPosition: [number, number];
  regionBbox?: [number, number, number, number];
  onPick: (lat: number, lng: number) => void;
}) {
  const bounds = regionBbox
    ? [[regionBbox[0], regionBbox[1]], [regionBbox[2], regionBbox[3]]] as [[number, number], [number, number]]
    : null;

  return (
    <div className="overflow-hidden rounded-xl border border-border" data-testid="field-report-map-picker">
      <MapContainer
        center={center}
        zoom={bounds ? 10 : 11}
        scrollWheelZoom={false}
        className="h-44 w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {bounds && (
          <Rectangle
            bounds={bounds}
            pathOptions={{
              color: '#f59e0b',
              weight: 1,
              fillOpacity: 0.02,
            }}
          />
        )}
        <CircleMarker
          center={markerPosition}
          radius={7}
          pathOptions={{
            color: '#ef4444',
            fillColor: '#f97316',
            fillOpacity: 0.9,
            weight: 2,
          }}
        />
        <LocationPickerInteraction onPick={onPick} />
      </MapContainer>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmitted?: (event: AvalancheEvent) => void;
  regionCenter?: [number, number];
  regionBbox?: [number, number, number, number];
  regionName?: string;
}

export default function FieldReportForm({
  open,
  onClose,
  onSubmitted,
  regionCenter,
  regionBbox,
  regionName,
}: Props) {
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [description, setDescription] = useState('');
  const [observedAt, setObservedAt] = useState(() => toDateTimeLocalValue(new Date()));
  const [submitting, setSubmitting] = useState(false);
  const [locating, setLocating] = useState(false);
  const online = useOnlineStatus();

  const setFallbackCoordinates = useCallback(() => {
    const fallbackLat = regionCenter?.[0] ?? 39.5;
    const fallbackLng = regionCenter?.[1] ?? -106.5;
    setLat(fallbackLat.toFixed(6));
    setLng(fallbackLng.toFixed(6));
  }, [regionCenter]);

  useEffect(() => {
    if (open) {
      setFallbackCoordinates();
      setObservedAt(toDateTimeLocalValue(new Date()));
    }
  }, [open, setFallbackCoordinates]);

  const buildQueuedReport = useCallback((
    clientReportId: string,
    reportLat: number,
    reportLng: number,
    reportDescription: string,
    reportObservedAt: string,
    userId?: string | null,
    submittedOffline?: boolean,
  ): QueuedFieldReport => ({
    id: clientReportId,
    clientReportId,
    lat: reportLat,
    lng: reportLng,
    description: reportDescription,
    observedAt: reportObservedAt,
    locationName: regionName ?? null,
    submittedOffline,
    createdAt: new Date().toISOString(),
    userId: userId ?? null,
  }), [regionName]);

  useEffect(() => {
    if (!online || !open) return;

    let cancelled = false;
    (async () => {
      try {
        const queued = await flushQueuedFieldReports(async (report) => {
          if (cancelled) return;
          await submitQueuedFieldReport(report);
        });
        if (!cancelled && queued > 0) {
          toast.success(`Synced ${queued} offline field report${queued === 1 ? '' : 's'}.`);
        }
      } catch (error) {
        if (!cancelled) {
          console.warn('Queued field report flush failed:', (error as Error).message);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [online, open]);

  const handleMapPick = useCallback((pickedLat: number, pickedLng: number) => {
    setLat(pickedLat.toFixed(6));
    setLng(pickedLng.toFixed(6));
  }, []);

  const handleUseMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      toast.error('Geolocation is unavailable in this browser');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude.toFixed(6));
        setLng(position.coords.longitude.toFixed(6));
        setLocating(false);
      },
      (error) => {
        setLocating(false);
        toast.error(error.message || 'Unable to access your location');
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 },
    );
  }, []);

  const resetForm = useCallback(() => {
    setDescription('');
    setObservedAt(toDateTimeLocalValue(new Date()));
    setFallbackCoordinates();
  }, [setFallbackCoordinates]);

  const handleSubmit = async () => {
    if (!description.trim()) {
      toast.error('Please provide a description');
      return;
    }

    if (!observedAt) {
      toast.error('Please provide the observation date and time');
      return;
    }

    const parsedLat = Number(lat);
    const parsedLng = Number(lng);
    if (!Number.isFinite(parsedLat) || !Number.isFinite(parsedLng)) {
      toast.error('Please enter valid latitude and longitude values');
      return;
    }
    if (parsedLat < -90 || parsedLat > 90) {
      toast.error('Invalid latitude. Must be between -90 and 90.');
      return;
    }
    if (parsedLng < -180 || parsedLng > 180) {
      toast.error('Invalid longitude. Must be between -180 and 180.');
      return;
    }
    if (submitting) {
      toast.info('Report already submitting...');
      return;
    }

    setSubmitting(true);
    let userId: string | null = null;
    const trimmedDescription = description.trim();
    const timestampIso = toObservedAtIso(observedAt);
    const clientReportId = buildClientReportId();
    const optimisticEvent = buildOptimisticFieldReportEvent({
      clientReportId,
      lat: parsedLat,
      lng: parsedLng,
      description: trimmedDescription,
      timestamp: timestampIso,
      locationName: regionName ?? '',
    });

    onSubmitted?.(optimisticEvent);

    try {
      const { data: { user } } = await supabase.auth.getUser();
      userId = user?.id ?? null;
      const queuedReport = buildQueuedReport(
        clientReportId,
        parsedLat,
        parsedLng,
        trimmedDescription,
        timestampIso,
        userId,
        !online,
      );

      if (!online) {
        await enqueueFieldReport(queuedReport);
        toast.info('Offline: report queued locally and will sync automatically when you reconnect');
        resetForm();
        onClose();
        return;
      }

      const submission = await submitQueuedFieldReport(queuedReport);
      onSubmitted?.(submission.event);
      toast.success(
        submission.promoted
          ? 'Field report submitted and corroborated'
          : 'Field report submitted and marked pending corroboration',
      );
      resetForm();
      onClose();
    } catch (err: unknown) {
      const queuedReport = buildQueuedReport(
        clientReportId,
        parsedLat,
        parsedLng,
        trimmedDescription,
        timestampIso,
        userId,
        true,
      );
      try {
        await enqueueFieldReport(queuedReport);
        toast.info('Network issue: report queued locally and will sync automatically');
        resetForm();
        onClose();
      } catch (queueErr) {
        console.error('field report submit failed', err);
        console.error('field report queue failed', queueErr);
        toast.error(err instanceof Error ? err.message : 'Failed to submit report');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const pickerCenter: [number, number] = [
    Number.isFinite(Number(lat)) ? Number(lat) : (regionCenter?.[0] ?? 39.5),
    Number.isFinite(Number(lng)) ? Number(lng) : (regionCenter?.[1] ?? -106.5),
  ];

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-lg border-border bg-card">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-foreground">
            <MapPin className="h-5 w-5 text-destructive" />
            Report Avalanche Observation
          </DialogTitle>
          <DialogDescription>
            Submit a field observation with an observed time, map location, and a short avalanche description.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!online && (
            <div
              role="status"
              className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-200"
            >
              <WifiOff className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                You appear to be offline. Your report will be saved locally and synced automatically as soon as your connection returns.
              </span>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Observation time</label>
            <div className="relative">
              <CalendarClock className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                aria-label="Observation time"
                type="datetime-local"
                value={observedAt}
                onChange={(event) => setObservedAt(event.target.value)}
                className="bg-secondary border-border pl-10"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs text-muted-foreground">Location picker</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="glass-panel border-0 text-xs"
                onClick={handleUseMyLocation}
                disabled={locating}
              >
                {locating ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <LocateFixed className="mr-1 h-3.5 w-3.5" />}
                Use my location
              </Button>
            </div>
            <LocationPickerMap
              center={pickerCenter}
              markerPosition={pickerCenter}
              regionBbox={regionBbox}
              onPick={handleMapPick}
            />
            <p className="text-[11px] text-muted-foreground">
              Click the mini-map or use your device location to place the report marker.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Latitude</label>
              <Input
                aria-label="Latitude"
                value={lat}
                onChange={(event) => setLat(event.target.value)}
                placeholder="39.5000"
                className="bg-secondary font-mono text-sm border-border"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Longitude</label>
              <Input
                aria-label="Longitude"
                value={lng}
                onChange={(event) => setLng(event.target.value)}
                placeholder="-106.5000"
                className="bg-secondary font-mono text-sm border-border"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Description</label>
            <Textarea
              aria-label="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the avalanche observation: type, size, aspect, elevation..."
              rows={4}
              className="bg-secondary border-border"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              className="rounded-xl"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              className="gap-2 rounded-xl bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Submit report
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
