-- M01-P08: required Postgres extensions for Vergeo5 (no domain tables).

create extension if not exists pgcrypto with schema extensions;
create extension if not exists pg_trgm with schema extensions;
create extension if not exists vector with schema extensions;
