import { useState, useCallback } from 'react';
import { MapPin, Camera, Send, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

export default function ReportPage() {
  const [lat, setLat] = useState<number | null>(null);
  const [lng, setLng] = useState<number | null>(null);
  const [description, setDescription] = useState('');
  const [estimatedSize, setEstimatedSize] = useState<string | null>(null);
  const [weatherConditions, setWeatherConditions] = useState('');
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  const useGeolocation = useCallback(() => {
    if (!navigator.geolocation) {
      setResult({ success: false, message: 'Geolocation not supported on this device.' });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude);
        setLng(pos.coords.longitude);
      },
      (err) => {
        setResult({ success: false, message: `Geolocation error: ${err.message}` });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);

  const handleSubmit = useCallback(async () => {
    if (lat == null || lng == null) {
      setResult({ success: false, message: 'Please provide a location.' });
      return;
    }
    if (description.trim().length < 10) {
      setResult({ success: false, message: 'Description must be at least 10 characters.' });
      return;
    }

    setSubmitting(true);
    setResult(null);

    try {
      // In production, this posts to Supabase citizen_reports table
      // For scaffold, we simulate a successful submission
      await new Promise((resolve) => setTimeout(resolve, 800));
      setResult({
        success: true,
        message: 'Report submitted successfully. Thank you for your contribution.',
      });
      setDescription('');
      setEstimatedSize(null);
      setWeatherConditions('');
      setPhotoUrl(null);
    } catch (err) {
      setResult({
        success: false,
        message: err instanceof Error ? err.message : 'Submission failed.',
      });
    } finally {
      setSubmitting(false);
    }
  }, [lat, lng, description]);

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-foreground">Report Avalanche Observation</h1>
          <p className="text-sm text-muted-foreground">
            Help improve avalanche safety by reporting what you see. Anonymous submissions welcome.
          </p>
        </div>

        {/* Location */}
        <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-3">
          <label className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
            Location
          </label>
          <div className="flex items-center gap-3">
            <button
              onClick={useGeolocation}
              className="flex items-center gap-2 rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary hover:bg-primary/20 transition-colors"
            >
              <MapPin className="h-4 w-4" />
              Use My Location
            </button>
            {lat != null && lng != null && (
              <span className="text-xs font-mono text-muted-foreground">
                {lat.toFixed(4)}°, {lng.toFixed(4)}°
              </span>
            )}
          </div>
          <p className="text-[10px] text-muted-foreground">
            Or click on the map to set location (coming soon).
          </p>
        </div>

        {/* Description */}
        <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-3">
          <label className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
            Description <span className="text-red-400">*</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what you observed (at least 10 characters)..."
            className="w-full min-h-[100px] rounded-lg border border-border/60 bg-background/40 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40"
            maxLength={2000}
          />
          <span className="text-[10px] text-muted-foreground">
            {description.length}/2000 characters
          </span>
        </div>

        {/* Optional fields */}
        <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-3">
          <label className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
            Additional Details (Optional)
          </label>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Estimated Size</label>
            <div className="flex gap-2">
              {['small', 'medium', 'large'].map((size) => (
                <button
                  key={size}
                  onClick={() => setEstimatedSize(estimatedSize === size ? null : size)}
                  className={`rounded-lg px-3 py-1.5 text-xs capitalize transition-colors ${
                    estimatedSize === size
                      ? 'bg-primary/20 text-primary'
                      : 'bg-background/30 text-muted-foreground hover:bg-background/50'
                  }`}
                >
                  {size}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Weather Conditions</label>
            <input
              type="text"
              value={weatherConditions}
              onChange={(e) => setWeatherConditions(e.target.value)}
              placeholder="e.g., Heavy snowfall, strong winds..."
              className="w-full rounded-lg border border-border/60 bg-background/40 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Photo</label>
            <button
              onClick={() => setPhotoUrl(photoUrl ? null : 'placeholder')}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                photoUrl
                  ? 'bg-green-500/15 text-green-400'
                  : 'bg-background/30 text-muted-foreground hover:bg-background/50'
              }`}
            >
              <Camera className="h-4 w-4" />
              {photoUrl ? 'Photo attached' : 'Add Photo'}
            </button>
          </div>
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={submitting || lat == null || description.trim().length < 10}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting...
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              Submit Report
            </>
          )}
        </button>

        {/* Result */}
        {result && (
          <div
            className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${
              result.success
                ? 'bg-green-500/10 text-green-400'
                : 'bg-red-500/10 text-red-400'
            }`}
          >
            {result.success ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0" />
            )}
            {result.message}
          </div>
        )}

        <p className="text-center text-[10px] text-muted-foreground/60">
          Reports are anonymous and used to improve avalanche forecasting.
          Rate limited to 5 submissions per hour.
        </p>
      </div>
    </div>
  );
}
