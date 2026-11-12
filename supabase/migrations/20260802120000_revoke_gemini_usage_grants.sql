-- FIX-6 (M-4): Revoke anon/authenticated grants on reserve_gemini_usage.
--
-- The original migration (20260720120000_atomic_gemini_spend_cap.sql) granted
-- EXECUTE to anon and authenticated, allowing any user to call the RPC
-- directly and exhaust the global spend cap, blocking all model calls.
--
-- This migration revokes those grants. Only service_role (used by edge
-- functions) should be able to call this function.
-- See audit finding M-4 and the Phase 5 remediation plan.

REVOKE ALL ON FUNCTION public.reserve_gemini_usage() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reserve_gemini_usage() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_gemini_usage() TO service_role;
