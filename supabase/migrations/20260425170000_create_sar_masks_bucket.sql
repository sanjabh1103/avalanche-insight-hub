-- Wave 3: storage bucket for SAR U-Net raster masks.
-- The worker writes GeoTIFF mask assets here and stores the resulting
-- storage object path in avalanche_events.mask_asset_ref.

INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'sar-masks',
  'sar-masks',
  FALSE,
  52428800,
  ARRAY['image/tiff', 'application/octet-stream']
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;
