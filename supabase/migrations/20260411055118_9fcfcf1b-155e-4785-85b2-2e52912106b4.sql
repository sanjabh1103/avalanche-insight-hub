-- Drop existing overly-permissive policies
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;

-- Allow anyone (including anonymous) to create field reports for public safety
CREATE POLICY "Anyone can submit field reports"
ON public.field_reports
FOR INSERT
TO public
WITH CHECK (true);

-- Only authenticated users can view their own reports
CREATE POLICY "Authenticated users can view own reports"
ON public.field_reports
FOR SELECT
TO authenticated
USING (auth.uid() = user_id);

-- Service role can view all (already exists, kept for admin access)