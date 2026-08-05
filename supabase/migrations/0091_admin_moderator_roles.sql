-- Day 35–36: additive superadmin + moderator roles for admin moderation workflows.
-- v1 `admin` remains valid; new roles are optional grants for separation of duties.

alter table public.user_roles
  drop constraint if exists user_roles_role_check;

alter table public.user_roles
  add constraint user_roles_role_check
  check (role in ('customer', 'vendor', 'admin', 'superadmin', 'moderator'));

comment on constraint user_roles_role_check on public.user_roles is
  'Platform roles. admin = legacy full admin; superadmin/moderator = roadmap RBAC slice.';
