// RLS Check Utility - Run this to verify RLS status
import { supabase } from './client';

export async function checkRLSStatus() {
  // Try to read without auth (should work for public tables)
  const { error: eventsError } = await supabase
    .from('avalanche_events')
    .select('count', { count: 'exact', head: true });

  console.log('Events table:', eventsError ? `Error: ${eventsError.message}` : 'Readable');

  // Try to insert without auth (should FAIL if RLS is properly configured)
  const { error: insertError } = await supabase
    .from('avalanche_events')
    .insert({ source: 'rls-test', description: 'Test' });

  console.log('Insert without auth:', insertError ? 
    `✅ BLOCKED (RLS working): ${insertError.message}` : 
    '❌ ALLOWED (RLS NOT working!)'
  );

  // Check field_reports (should require auth)
  const { error: reportsError } = await supabase
    .from('field_reports')
    .select('count', { count: 'exact', head: true });

  console.log('Field reports (auth required):', reportsError ? 
    `✅ Protected: ${reportsError.message}` : 
    '⚠️ May be readable'
  );

  return { eventsError, insertError, reportsError };
}

// Run: import { checkRLSStatus } from './check-rls'; checkRLSStatus();
