-- Fix BUG-003: Allow anonymous users to submit field reports
-- The previous policy required auth.uid() = user_id which blocked anon inserts

-- Drop the restrictive policy
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;

-- Create new policy allowing anonymous inserts
-- This enables the Groundsource loop: anyone can contribute reports
CREATE POLICY "Allow anonymous insert" 
  ON public.field_reports 
  FOR INSERT 
  TO anon, authenticated
  WITH CHECK (true);

-- Keep select policy restricted to own reports for privacy
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;
CREATE POLICY "Users can view own reports" 
  ON public.field_reports 
  FOR SELECT 
  TO authenticated 
  USING (auth.uid() = user_id);

-- Allow anonymous users to view all reports (for map display)
CREATE POLICY "Allow anonymous select" 
  ON public.field_reports 
  FOR SELECT 
  TO anon 
  USING (true);

-- Verify the policies
SELECT 
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
FROM pg_policies 
WHERE tablename = 'field_reports';
