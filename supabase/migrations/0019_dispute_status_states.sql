-- M09-P09: Widen disputes.status CHECK for under_review + resolved_partial.
--
-- Reversible rollback (restore 0007 constraint set):
--   ALTER TABLE public.disputes DROP CONSTRAINT disputes_status_check;
--   ALTER TABLE public.disputes ADD CONSTRAINT disputes_status_check
--     CHECK (status IN (
--       'open', 'vendor_responded', 'resolved_refund', 'resolved_release', 'rejected'
--     ));

ALTER TABLE public.disputes DROP CONSTRAINT disputes_status_check;

ALTER TABLE public.disputes
  ADD CONSTRAINT disputes_status_check
  CHECK (status IN (
    'open',
    'vendor_responded',
    'under_review',
    'resolved_refund',
    'resolved_release',
    'resolved_partial',
    'rejected'
  ));
