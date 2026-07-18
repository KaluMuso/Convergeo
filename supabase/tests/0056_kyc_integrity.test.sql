-- pgTAP checks for 0056_kyc_integrity (run via supabase test db when available).
begin;
select plan(8);

select has_column('public', 'kyc_records', 'reviewed_by', 'reviewed_by column exists');
select has_column('public', 'kyc_records', 'reviewed_at', 'reviewed_at column exists');
select has_column('public', 'kyc_records', 'decision_reason', 'decision_reason column exists');
select has_column('public', 'kyc_records', 'lifecycle_reason', 'lifecycle_reason column exists');

select has_view('public', 'kyc_orphaned_tier_report', 'orphan report view exists');

select ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.kyc_records'::regclass
      and conname = 'kyc_records_status_check'
  ),
  'kyc_records status check constraint present'
);

select ok(
  pg_get_constraintdef(
    (
      select oid
      from pg_constraint
      where conrelid = 'public.kyc_records'::regclass
        and conname = 'kyc_records_status_check'
    )
  ) like '%submitted%'
    and pg_get_constraintdef(
      (
        select oid
        from pg_constraint
        where conrelid = 'public.kyc_records'::regclass
          and conname = 'kyc_records_status_check'
      )
    ) like '%under_review%'
    and pg_get_constraintdef(
      (
        select oid
        from pg_constraint
        where conrelid = 'public.kyc_records'::regclass
          and conname = 'kyc_records_status_check'
      )
    ) like '%suspended%'
    and pg_get_constraintdef(
      (
        select oid
        from pg_constraint
        where conrelid = 'public.kyc_records'::regclass
          and conname = 'kyc_records_status_check'
      )
    ) like '%revoked%',
  'status check includes submitted/under_review/suspended/revoked'
);

select ok(
  exists (
    select 1
    from pg_trigger
    where tgrelid = 'public.kyc_records'::regclass
      and tgname = 'kyc_records_guard_integrity'
  ),
  'integrity guard trigger installed'
);

select * from finish();
rollback;
