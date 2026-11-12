DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'field_reports_location_valid_range'
  ) THEN
    ALTER TABLE public.field_reports
      ADD CONSTRAINT field_reports_location_valid_range
      CHECK (
        location IS NULL
        OR (
          ST_Y(location::extensions.geometry) BETWEEN -90 AND 90
          AND ST_X(location::extensions.geometry) BETWEEN -180 AND 180
        )
      );
  END IF;
END $$;

