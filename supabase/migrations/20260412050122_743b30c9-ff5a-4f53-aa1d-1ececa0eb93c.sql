
CREATE TABLE public.user_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  endpoint text NOT NULL,
  p256dh text NOT NULL,
  auth_key text NOT NULL,
  region_bbox numeric[] DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can subscribe to alerts"
  ON public.user_alerts FOR INSERT
  TO public
  WITH CHECK (true);

CREATE POLICY "Service role can manage alerts"
  ON public.user_alerts FOR ALL
  TO public
  USING (auth.role() = 'service_role');
