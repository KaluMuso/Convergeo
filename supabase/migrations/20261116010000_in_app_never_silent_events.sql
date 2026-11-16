-- In-app rows for the never-silent lifecycle templates (E1/E4 follow-up).
--
-- Extends private.in_app_from_outbox() so the outbox templates added by the
-- notification registry also write their in-app row in the same transaction:
-- order_cancelled, order_completed, payment_failed, payout_sent, payout_failed,
-- dispute_resolved, service_quote_accepted (vendor "quote_accepted").
-- dispute_opened / ticket_issued are intentionally NOT handled here: the
-- disputes/tickets table triggers already write them (no duplicates).
--
-- Additive: create or replace of one function; the trigger is untouched. A writer
-- failure stays a WARNING (the existing exception block), so a notification bug
-- can never roll back an order, payment or payout.
--
-- DOWN (manual; restores the previous body from 20261113130000_in_app_notifications.sql):
-- create or replace function private.in_app_from_outbox()
-- returns trigger
-- language plpgsql
-- security definer
-- set search_path = public, private
-- as $$
-- declare
--   v_payload jsonb := coalesce(new.payload, '{}'::jsonb);
--   v_order uuid := private.in_app_try_uuid(v_payload ->> 'order_id');
--   v_recipient uuid := private.in_app_try_uuid(v_payload ->> 'recipient_id');
--   v_vendor uuid := private.in_app_try_uuid(v_payload ->> 'vendor_id');
--   v_thread uuid := private.in_app_try_uuid(v_payload ->> 'thread_id');
--   v_job uuid := private.in_app_try_uuid(v_payload ->> 'job_id');
--   v_owner uuid;
--   v_status_type text;
-- begin
--   case new.template
--     when 'vendor_new_order' then
--       perform private.in_app_for_order(v_order, 'order_placed', true, true);
--
--     when 'order_status_changed' then
--       -- Vendor-driven transitions (vendor_orders router). There is no Meta
--       -- template for this outbox row, so before this migration the customer
--       -- received nothing at all when a vendor confirmed/packed/shipped.
--       v_status_type := case v_payload ->> 'to_status'
--         when 'confirmed' then 'order_confirmed'
--         when 'cancelled' then 'order_rejected'
--         when 'processing' then 'order_packed'
--         when 'shipped' then 'order_shipped'
--         when 'ready' then 'order_ready_pickup'
--         when 'delivered' then 'order_delivered'
--         else null
--       end;
--       if v_status_type is not null then
--         perform private.in_app_for_order(
--           v_order, v_status_type, true, v_status_type = 'order_delivered'
--         );
--       end if;
--
--     when 'order_confirmed', 'order_shipped', 'order_ready_pickup' then
--       perform private.in_app_for_order(v_order, new.template, true, false);
--
--     when 'order_delivered' then
--       perform private.in_app_for_order(v_order, 'order_delivered', true, true);
--
--     when 'kyc_approved', 'kyc_rejected' then
--       select owner_user_id into v_owner from public.vendors where id = v_vendor;
--       perform private.enqueue_in_app_notification(
--         v_owner, 'vendor', new.template, '{}'::jsonb, '/onboarding/status',
--         split_part(new.dedupe_key, ':', 1) || ':' || split_part(new.dedupe_key, ':', 2)
--       );
--
--     when 'rfq_opened' then
--       if v_thread is not null then
--         perform private.enqueue_in_app_notification(
--           v_recipient, 'vendor', 'rfq_received', '{}'::jsonb, '/rfq',
--           'rfq_received:' || v_thread::text
--         );
--       end if;
--
--     when 'rfq_quoted' then
--       if v_thread is not null then
--         perform private.enqueue_in_app_notification(
--           v_recipient, 'customer', 'quote_received', '{}'::jsonb,
--           '/account/quotes/' || v_thread::text, 'quote_received:' || new.dedupe_key
--         );
--       end if;
--
--     when 'rfq_job_broadcast' then
--       if v_job is not null then
--         perform private.enqueue_in_app_notification(
--           v_recipient, 'vendor', 'job_matched', '{}'::jsonb, '/jobs',
--           'job_matched:' || v_job::text
--         );
--       end if;
--
--     else
--       null;
--   end case;
--   return null;
-- exception
--   when others then
--     raise warning 'in_app_from_outbox skipped (template %, sqlstate %): %',
--       new.template, sqlstate, sqlerrm;
--     return null;
-- end;
-- $$;

create or replace function private.in_app_from_outbox()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_payload jsonb := coalesce(new.payload, '{}'::jsonb);
  v_order uuid := private.in_app_try_uuid(v_payload ->> 'order_id');
  v_recipient uuid := private.in_app_try_uuid(v_payload ->> 'recipient_id');
  v_vendor uuid := private.in_app_try_uuid(v_payload ->> 'vendor_id');
  v_thread uuid := private.in_app_try_uuid(v_payload ->> 'thread_id');
  v_job uuid := private.in_app_try_uuid(v_payload ->> 'job_id');
  v_owner uuid;
  v_status_type text;
begin
  case new.template
    when 'vendor_new_order' then
      perform private.in_app_for_order(v_order, 'order_placed', true, true);

    when 'order_status_changed' then
      -- Vendor-driven transitions (vendor_orders router). There is no Meta
      -- template for this outbox row, so before this migration the customer
      -- received nothing at all when a vendor confirmed/packed/shipped.
      v_status_type := case v_payload ->> 'to_status'
        when 'confirmed' then 'order_confirmed'
        when 'cancelled' then 'order_rejected'
        when 'processing' then 'order_packed'
        when 'shipped' then 'order_shipped'
        when 'ready' then 'order_ready_pickup'
        when 'delivered' then 'order_delivered'
        else null
      end;
      if v_status_type is not null then
        perform private.in_app_for_order(
          v_order, v_status_type, true, v_status_type = 'order_delivered'
        );
      end if;

    when 'order_confirmed', 'order_shipped', 'order_ready_pickup' then
      perform private.in_app_for_order(v_order, new.template, true, false);

    when 'order_delivered' then
      perform private.in_app_for_order(v_order, 'order_delivered', true, true);

    when 'kyc_approved', 'kyc_rejected' then
      select owner_user_id into v_owner from public.vendors where id = v_vendor;
      perform private.enqueue_in_app_notification(
        v_owner, 'vendor', new.template, '{}'::jsonb, '/onboarding/status',
        split_part(new.dedupe_key, ':', 1) || ':' || split_part(new.dedupe_key, ':', 2)
      );

    when 'rfq_opened' then
      if v_thread is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'vendor', 'rfq_received', '{}'::jsonb, '/rfq',
          'rfq_received:' || v_thread::text
        );
      end if;

    when 'rfq_quoted' then
      if v_thread is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'customer', 'quote_received', '{}'::jsonb,
          '/account/quotes/' || v_thread::text, 'quote_received:' || new.dedupe_key
        );
      end if;

    when 'rfq_job_broadcast' then
      if v_job is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'vendor', 'job_matched', '{}'::jsonb, '/jobs',
          'job_matched:' || v_job::text
        );
      end if;

    when 'order_cancelled' then
      -- A vendor rejection already wrote the customer's order_rejected row.
      if not exists (
        select 1 from public.in_app_notifications
        where audience = 'customer'
          and dedupe_key = 'order_rejected:' || coalesce(v_order::text, '')
      ) then
        perform private.in_app_for_order(v_order, 'order_cancelled', true, false);
      end if;

    when 'order_completed' then
      perform private.in_app_for_order(v_order, 'order_completed', true, false);

    when 'payment_failed' then
      perform private.enqueue_in_app_notification(
        v_recipient, 'customer', 'payment_failed', '{}'::jsonb, '/account/orders',
        'payment_failed:' || new.dedupe_key
      );

    when 'payout_sent', 'payout_failed' then
      perform private.enqueue_in_app_notification(
        v_recipient, 'vendor', new.template, '{}'::jsonb, '/payouts',
        new.template || ':' || new.dedupe_key
      );

    when 'dispute_resolved' then
      if v_order is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'customer', 'dispute_resolved',
          jsonb_build_object('ref', private.in_app_short_ref(v_order)),
          '/account/orders/' || v_order::text, 'dispute_resolved:' || new.dedupe_key
        );
      end if;

    when 'service_quote_accepted' then
      perform private.enqueue_in_app_notification(
        v_recipient, 'vendor', 'quote_accepted', '{}'::jsonb, '/jobs',
        'quote_accepted:' || new.dedupe_key
      );

    -- dispute_opened and ticket_issued are written by their domain-table triggers
    -- (disputes_in_app / tickets_in_app); the outbox rows must not duplicate them.

    else
      null;
  end case;
  return null;
exception
  when others then
    raise warning 'in_app_from_outbox skipped (template %, sqlstate %): %',
      new.template, sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_outbox() from public, anon, authenticated;
