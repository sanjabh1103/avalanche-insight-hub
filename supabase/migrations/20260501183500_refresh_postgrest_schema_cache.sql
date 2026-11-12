-- Operational recovery for a live PostgREST schema cache failure.
-- Safe to run more than once.
select pg_notification_queue_usage();
notify pgrst, 'reload schema';
