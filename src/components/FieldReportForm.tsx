import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MapPin, Send, Loader2, WifiOff } from 'lucide-react';
import { toast } from 'sonner';
import type { AvalancheEvent } from '@/components/HistoricalEventsToggle';
import {
  enqueueFieldReport,
  flushQueuedFieldReports,
  type QueuedFieldReport,
} from '@/lib/offlineFieldReports';
import { submitQueuedFieldReport } from '@/lib/fieldReportSync';
import { supabase } from '@/integrations/supabase/client';

// Story 17: lightweight online/offline hook used to show users when their
// submission will be queued by the Workbox BackgroundSync plugin.
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

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmitted?: (event: AvalancheEvent) => void;
  regionCenter?: [number, number];
}

export default function FieldReportForm({ open, onClose, onSubmitted, regionCenter }: Props) {
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const online = useOnlineStatus();

  const setFallbackCoordinates = useCallback(() => {
    const fallbackLat = regionCenter?.[0] ?? 39.5;
    const fallbackLng = regionCenter?.[1] ?? -106.5;
    setLat(fallbackLat.toFixed(4));
    setLng(fallbackLng.toFixed(4));
  }, [regionCenter]);

  useEffect(() => {
    if (open) {
      setFallbackCoordinates();
    }
  }, [open, setFallbackCoordinates]);

  const buildQueuedReport = useCallback((
    clientReportId: string,
    reportLat: number,
    reportLng: number,
    reportDescription: string,
    userId?: string | null,
  ): QueuedFieldReport => ({
    id: clientReportId,
    clientReportId,
    lat: reportLat,
    lng: reportLng,
    description: reportDescription,
    createdAt: new Date().toISOString(),
    userId: userId ?? null,
  }), []);

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
          toast.success(`Syncing ${queued} offline report${queued === 1 ? '' : 's'}...`);
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

  const handleSubmit = async () => {
    if (!description.trim()) {
      toast.error('Please provide a description');
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

    // BUG-02 fix: Prevent duplicate submissions while one is in flight
    if (submitting) {
      toast.info('Report already submitting...');
      return;
    }

    setSubmitting(true);
    let userId: string | null = null;

    try {
      const { data: { user } } = await supabase.auth.getUser();
      userId = user?.id ?? null;
      const idSeed = `${user?.id || 'anon'}|${parsedLat.toFixed(6)}|${parsedLng.toFixed(6)}|${description.trim().toLowerCase()}`;
      const clientReportId = `field-${btoa(unescape(encodeURIComponent(idSeed))).replace(/=+$/g, '').slice(0, 24)}`;
      const queuedReport = buildQueuedReport(clientReportId, parsedLat, parsedLng, description.trim(), userId);

      if (!online) {
        await enqueueFieldReport(queuedReport);
        onSubmitted?.({
          id: `queued-${clientReportId}`,
          lat: parsedLat,
          lng: parsedLng,
          severity: 3,
          confidence: 0.6,
          description: description.trim(),
          source: 'field_report',
          event_type: 'unknown',
          timestamp: queuedReport.createdAt,
          location_name: '',
        });
        toast.info('Offline: report queued locally and will sync automatically when you reconnect');
        setDescription('');
        onClose();
        return;
      }

      await submitQueuedFieldReport(queuedReport);
      onSubmitted?.({
        id: `field-report-${Date.now()}`,
        lat: parsedLat,
        lng: parsedLng,
        severity: 3,
        confidence: 0.6,
        description: description.trim(),
        source: 'field_report',
        event_type: 'unknown',
        timestamp: new Date().toISOString(),
        location_name: '',
      });
      toast.success('Field report submitted successfully');

      setDescription('');
      onClose();
    } catch (err: unknown) {
      const idSeed = `${userId || 'anon'}|${parsedLat.toFixed(6)}|${parsedLng.toFixed(6)}|${description.trim().toLowerCase()}`;
      const clientReportId = `field-${btoa(unescape(encodeURIComponent(idSeed))).replace(/=+$/g, '').slice(0, 24)}`;
      const queuedReport = buildQueuedReport(clientReportId, parsedLat, parsedLng, description.trim(), userId);
      try {
        await enqueueFieldReport(queuedReport);
        onSubmitted?.({
          id: `queued-${clientReportId}`,
          lat: parsedLat,
          lng: parsedLng,
          severity: 3,
          confidence: 0.6,
          description: description.trim(),
          source: 'field_report',
          event_type: 'unknown',
          timestamp: queuedReport.createdAt,
          location_name: '',
        });
        toast.info('Network issue: report queued locally and will sync automatically');
        setDescription('');
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

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-card border-border max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-foreground">
            <MapPin className="h-5 w-5 text-destructive" />
            Report Avalanche Observation
          </DialogTitle>
          <DialogDescription>
            Submit a field observation with coordinates and a short avalanche description.
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
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Latitude</label>
              <Input
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                placeholder="39.5000"
                className="font-mono text-sm bg-secondary border-border"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Longitude</label>
              <Input
                value={lng}
                onChange={(e) => setLng(e.target.value)}
                placeholder="-106.5000"
                className="font-mono text-sm bg-secondary border-border"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Description</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the avalanche observation: type, size, aspect, elevation..."
              rows={4}
              className="bg-secondary border-border"
            />
          </div>
          <Button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            Submit Report
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
