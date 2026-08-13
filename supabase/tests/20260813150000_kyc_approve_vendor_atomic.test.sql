-- pgTAP checks for 20260813150000_kyc_approve_vendor_atomic.sql

select has_function(
  'public',
  'approve_kyc_vendor',
  array['uuid', 'uuid', 'integer', 'text'],
  'approve_kyc_vendor function exists'
);

select function_returns(
  'public',
  'approve_kyc_vendor',
  array['uuid', 'uuid', 'integer', 'text'],
  'jsonb',
  'approve_kyc_vendor returns jsonb'
);

select ok(
  (
    select count(*) = 0
    from aclexplode(
      (select proacl from pg_proc where proname = 'approve_kyc_vendor')
    ) acl
    where acl.grantee::regrole::text in ('public', 'anon', 'authenticated')
  ),
  'approve_kyc_vendor is not executable by public/anon/authenticated'
);

select ok(
  has_function_privilege('service_role', 'public.approve_kyc_vendor(uuid, uuid, integer, text)', 'EXECUTE'),
  'service_role may execute approve_kyc_vendor'
);
