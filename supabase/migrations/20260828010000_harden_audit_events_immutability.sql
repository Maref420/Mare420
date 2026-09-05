-- Remove the out-of-band write policy for client roles.
DROP POLICY IF EXISTS audit_events_append
ON public.audit_events;

-- Audit events are backend-owned.
REVOKE ALL
ON public.audit_events
FROM anon, authenticated;

-- service_role may append and read audit events, but may not mutate
-- or truncate existing audit records.
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON public.audit_events
FROM service_role;

GRANT INSERT, SELECT
ON public.audit_events
TO service_role;

-- Defense-in-depth: reject UPDATE/DELETE at the database boundary.
CREATE OR REPLACE FUNCTION public.prevent_audit_events_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    RAISE EXCEPTION
        'audit_events is immutable: % is not permitted',
        TG_OP;
END;
$function$;

DROP TRIGGER IF EXISTS audit_events_immutable
ON public.audit_events;

CREATE TRIGGER audit_events_immutable
BEFORE UPDATE OR DELETE
ON public.audit_events
FOR EACH ROW
EXECUTE FUNCTION public.prevent_audit_events_mutation();

REVOKE EXECUTE
ON FUNCTION public.prevent_audit_events_mutation()
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE
ON FUNCTION public.prevent_audit_events_mutation()
TO service_role;
