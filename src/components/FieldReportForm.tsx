import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MapPin, Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function FieldReportForm({ open, onClose }: Props) {
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const setFallbackCoordinates = useCallback(() => {
    setLat('39.5');
    setLng('-106.5');
    toast.info('Using region center because browser geolocation is unavailable or was denied.');
  }, []);

  useEffect(() => {
    if (open && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLat(pos.coords.latitude.toFixed(6));
          setLng(pos.coords.longitude.toFixed(6));
        },
        setFallbackCoordinates,
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
      );
    } else if (open) {
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
      const { data, error } = await supabase.from('field_reports').insert({
        user_id: user?.id,
        description: description.trim(),
        location: `SRID=4326;POINT(${parsedLng} ${parsedLat})` as unknown,
      }).select('id').single();
      if (error) throw error;

      if (data?.id) {
        await supabase.functions.invoke('field-report-enrichment', {
          body: {
            fieldReportId: data.id,
            lat: parsedLat,
            lng: parsedLng,
            description: description.trim(),
          },
        });
      }

      toast.success('Field report submitted');
      setDescription('');
      onClose();
    } catch (err: unknown) {
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
