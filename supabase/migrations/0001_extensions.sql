-- M01-P08: base extensions (no domain tables — M03 owns schema)
create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists vector;
