-- Local pgTAP role-management contract. All fixture accounts roll back.
begin;
set local search_path to public, extensions, auth;
select extensions.plan(13);

select extensions.has_table('public', 'admin_roles', 'restricted role definitions exist');
select extensions.has_function('public', 'manage_admin_role',
  array['uuid','text','text','text','text[]','uuid'], 'atomic role-management RPC exists');
select extensions.ok(
  has_function_privilege('service_role',
    'public.manage_admin_role(uuid,text,text,text,text[],uuid)', 'EXECUTE'),
  'service role may call management RPC');
select extensions.ok(
  not has_function_privilege('authenticated',
    'public.manage_admin_role(uuid,text,text,text,text[],uuid)', 'EXECUTE'),
  'browser identities cannot call management RPC');

-- Only identity fields shared by GoTrue and the canonical bare-PG replay shim.
insert into auth.users(id,email)
values
  ('a00a0000-0000-0000-0000-000000000001','rbac-a@test.local'),
  ('a00a0000-0000-0000-0000-000000000002','rbac-b@test.local');
insert into public.profiles(id)
values ('a00a0000-0000-0000-0000-000000000001'),
       ('a00a0000-0000-0000-0000-000000000002')
on conflict do nothing;
insert into public.user_roles(user_id,role)
values ('a00a0000-0000-0000-0000-000000000001','superadmin');

set local role service_role;
select extensions.throws_ok(
  $$select public.manage_admin_role('a00a0000-0000-0000-0000-000000000002',
    'create','rbac_rogue','Rogue',array['finance.read'],null)$$,
  '42501', null, 'restricted account cannot create a role');
select extensions.throws_ok(
  $$select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
    'create','rbac_invalid','Invalid',array['payments.transfer'],null)$$,
  '23514', null, 'transfer permission is not a valid grant');
select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
  'create','rbac_finance_test','Finance test',array['finance.read'],null);
select extensions.ok(exists(select 1 from public.admin_roles where key='rbac_finance_test'),
  'superadmin created a restricted role');
select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
  'assign','rbac_finance_test',null,null,'a00a0000-0000-0000-0000-000000000002');
select extensions.ok(exists(select 1 from public.user_roles
  where user_id='a00a0000-0000-0000-0000-000000000002' and role='rbac_finance_test'),
  'assignment uses the existing user_roles table');
select extensions.throws_ok(
  $$select public.manage_admin_role('a00a0000-0000-0000-0000-000000000002',
    'assign','superadmin',null,null,'a00a0000-0000-0000-0000-000000000002')$$,
  '42501', null, 'restricted account cannot promote itself');
select extensions.throws_ok(
  $$select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
    'revoke','superadmin',null,null,'a00a0000-0000-0000-0000-000000000001')$$,
  '23514', null, 'last superadmin cannot be removed');
select extensions.throws_ok(
  $$select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
    'delete','rbac_finance_test',null,null,null)$$,
  '23503', null, 'assigned role cannot be deleted');
insert into public.user_roles(user_id,role)
values ('a00a0000-0000-0000-0000-000000000002','admin');
select public.manage_admin_role('a00a0000-0000-0000-0000-000000000001',
  'revoke','admin',null,null,'a00a0000-0000-0000-0000-000000000002');
select extensions.ok(not exists(select 1 from public.user_roles
  where user_id='a00a0000-0000-0000-0000-000000000002' and role='admin'),
  'superadmin may revoke a legacy admin assignment');
select extensions.is((select count(*)::integer from public.audit_log
  where actor='a00a0000-0000-0000-0000-000000000001' and action like 'admin.role.%'),
  3, 'only successful changes are audited');

select * from extensions.finish();
rollback;
