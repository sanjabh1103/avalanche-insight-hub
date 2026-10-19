-- Atomic Gemini spend-cap reservation RPC.
--
-- Replaces the read-check-call-increment pattern in edge functions with a single
-- atomic Postgres operation that increments gemini_usage only if the cap has not
-- been reached. This prevents concurrent requests from overshooting the cap.
--
-- Returns JSON: { "reserved": boolean, "usage": integer, "cap": integer }
--   reserved = true  -> caller may proceed with the Gemini API call
--   reserved = false -> cap exceeded, caller must skip the Gemini API call

CREATE OR REPLACE FUNCTION public.reserve_gemini_usage()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_id UUID;
  v_usage INTEGER;
  v_cap INTEGER;
  v_reserved BOOLEAN := false;
BEGIN
  -- Try to find the existing config row
  SELECT id, gemini_usage, gemini_spend_cap
    INTO v_id, v_usage, v_cap
  FROM public.system_config
  LIMIT 1
  FOR UPDATE;

  IF v_id IS NULL THEN
    -- No config row yet; insert with cap=1000 and reserve the first slot
    INSERT INTO public.system_config (gemini_usage, gemini_spend_cap)
    VALUES (1, 1000)
    RETURNING gemini_usage, gemini_spend_cap INTO v_usage, v_cap;
    v_reserved := true;
  ELSIF v_usage < v_cap THEN
    -- Atomically increment only if under cap
    UPDATE public.system_config
      SET gemini_usage = gemini_usage + 1
    WHERE id = v_id AND gemini_usage < gemini_spend_cap
    RETURNING gemini_usage, gemini_spend_cap INTO v_usage, v_cap;
    v_reserved := true;
  ELSE
    -- Cap exceeded; do not increment
    v_reserved := false;
  END IF;

  RETURN jsonb_build_object(
    'reserved', v_reserved,
    'usage', v_usage,
    'cap', v_cap
  );
END;
$$;

-- Grant execute to anon and authenticated (edge functions use service role)
GRANT EXECUTE ON FUNCTION public.reserve_gemini_usage() TO anon, authenticated;
