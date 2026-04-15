import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MapPin, Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import type { AvalancheEvent } from '@/components/HistoricalEventsToggle';

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

    setSubmitting(true);
    try {
      const { data: { user } } = await supabase.auth.getUser();
      const { data: report, error } = await supabase.from('field_reports').insert({
        user_id: user?.id,
        hazard_type: 'avalanche',
        review_status: 'pending',
        training_eligible: false,
        description: description.trim(),
        location: `SRID=4326;POINT(${parsedLng} ${parsedLat})` as unknown,
      }).select('id').single();
      if (error) throw error;
      if (!report?.id) {
        throw new Error('Failed to create field report');
      }

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

      // B9 fix: Show success toast immediately after successful insert (before enrichment and close)
      toast.success('Field report submitted successfully');

      // Fire enrichment async - don't block UI on this
      supabase.functions.invoke('field-report-enrichment', {
        body: {
          fieldReportId: report.id,
          lat: parsedLat,
          lng: parsedLng,
          description: description.trim(),
          hazard_type: 'avalanche',
        },
      }).then(({ error: enrichmentError }) => {
        if (enrichmentError) {
          console.error('field-report-enrichment failed', enrichmentError);
        }
      });

      setDescription('');
      onClose();
    } catch (err: unknown) {
      console.error('field report submit failed', err);
      toast.error(err instanceof Error ? err.message : 'Failed to submit report');
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
