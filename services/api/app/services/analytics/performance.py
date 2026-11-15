"""Performance dashboard: what to boost and what to uproot.

Scorecards for **categories, products, vendors and clips** over a reporting window
(Africa/Lusaka days, OD-9), each with the funnel **views -> add-to-cart -> paid orders**,
conversion, repeat rate and (finance callers only) item sales and contribution. Plus a
per-order **contribution** block: what the platform keeps from a paid order after the
payment fee, the courier and refunds. Cohort retention lives on the Users report.

Definitions (also the export column meanings):

* **views** - product-page views from ``listing_analytics.pdp_views`` (deduplicated per
  viewer session per day at write time). Clip **views** come from ``clip_views`` (the
  >=3 s rule, one per signed-in viewer per day). Both counters are bucketed by the UTC
  day they were written on (they cannot be re-bucketed), so at a window edge up to two
  hours of views can fall on the neighbouring Lusaka day.
* **carts** - add-to-cart actions: ``funnel_events`` ``cart_add`` lines for the listing,
  created in the window. A clip's carts are the lines the server attributed to it.
* **orders** - distinct paid, not cancelled orders (``PAID_ORDERS_SQL``) created in the
  window that contain the listing. A clip's orders are **clip-assisted**: a paid order
  line whose customer added that listing to the cart from the clip in the 7 days before
  the order (last clip wins).
* **customers** / **repeat customers** - distinct buyers in the window, and those with
  two or more such orders in the window. ``repeat_rate_bps`` = repeat / customers.
* **returning customers** (platform) - window buyers who had a paid order before it.
* **contribution** of a paid order = commission (from the order's commission snapshot,
  ``line_total * rate_bps // 10000`` per line, as the commission engine) + delivery fee
  charged - payment fee - courier cost - refund loss, where

  - **payment fee** is the Lenco collection fee booked in the ledger (``lenco_fee``
    postings on the checkout group's successful payments), shared across the group's
    orders by value; orders whose group has no booked fee are counted in
    ``fee_unbooked_orders`` (fee 0 for them);
  - **courier cost** is the quoted price of the latest dispatch that was not cancelled;
    delivery orders without one are counted in ``courier_cost_unknown_orders`` (cost 0);
  - **refund loss** is the part of commission + delivery fee the platform gives up on
    completed refunds, in proportion to the refunded share of the order value.

  An entity's contribution is the sum of its order lines' share of each order's
  contribution (by line value, rounded towards zero).

Ranking. **Top** = most paid orders (then units, then views). **Bottom** (uproot
candidates) = among entities with at least ``MIN_VIEWS`` views, the lowest view-to-order
conversion (then most views): attention that does not turn into sales. **Hidden gems**
(boost candidates) = at least ``MIN_ORDERS`` orders, highest view-to-order conversion,
then fewest views: things that sell when seen but are not seen enough.

Money is integer ngwee; rates are integer basis points. Counts only for analytics.read
callers: item sales and contribution are ``None`` without finance.read/finance.operate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal

from app.services.analytics.dashboards import (
    Window,
    _d,
    _ints,
    _rows,
    in_window,
    lower_bound,
    rate_bps,
    upper_bound,
)

Grain = Literal["categories", "products", "vendors", "clips"]
GRAINS: Final[tuple[Grain, ...]] = ("categories", "products", "vendors", "clips")

LIST_SIZE: Final = 10
MIN_VIEWS: Final = 20
MIN_ORDERS: Final = 2
CLIP_ATTRIBUTION_DAYS: Final = 7

_UUID_RE: Final = "'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'"


def _clean(expr: str) -> str:
    """A label as one psql-safe cell (no field separator, no newline)."""
    return f"replace(replace(coalesce({expr}, ''), '|', '/'), E'\\n', ' ')"


# A paid, not cancelled order created in [start, end] (Lusaka), with the columns the
# contribution model needs. Same predicate as dashboards.PAID_ORDERS_SQL.
def _paid_orders(start: date, end: date) -> str:
    return (
        "SELECT o.id, o.customer_id, o.vendor_id, o.checkout_group_id, o.created_at, "
        "o.fulfilment, o.delivery_fee_ngwee, o.commission_snapshot FROM public.orders o "
        "WHERE o.status <> 'cancelled' AND EXISTS (SELECT 1 FROM public.payments p "
        "WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success') "
        f"AND {in_window('o.created_at', start, end)}"
    )


def _cart_lines(since_sql: str, end: date) -> str:
    return (
        "SELECT (line ->> 'listing_id')::uuid AS listing_id, "
        "CASE WHEN line ->> 'clip_id' ~ " + _UUID_RE + " THEN (line ->> 'clip_id')::uuid END "
        "AS clip_id, fe.customer_id, fe.created_at FROM public.funnel_events fe "
        "CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(fe.snapshot -> 'lines') "
        "= 'array' THEN fe.snapshot -> 'lines' ELSE '[]'::jsonb END) AS line "
        f"WHERE fe.stage = 'cart_add' AND fe.created_at >= {since_sql} "
        f"AND fe.created_at < {upper_bound(end)} AND line ->> 'listing_id' ~ {_UUID_RE}"
    )


def _contribution_cte(*, finance: bool) -> str:
    """``oc``: one row per paid order in ``po`` with the contribution components."""
    if not finance:
        return (
            "oc AS (SELECT po.id AS order_id, 0::bigint AS items_ngwee, "
            "0::bigint AS contribution_ngwee FROM po)"
        )
    return (
        # Value of every order of a paid group (cancelled ones too: the fee covered them).
        "gv AS (SELECT o.checkout_group_id, sum(o.delivery_fee_ngwee + coalesce((SELECT "
        "sum(oi.qty::bigint * oi.unit_price_ngwee) FROM public.order_items oi "
        "WHERE oi.order_id = o.id), 0))::bigint AS value FROM public.orders o "
        "WHERE o.checkout_group_id IN (SELECT checkout_group_id FROM po) GROUP BY 1), "
        "gf AS (SELECT p.checkout_group_id, sum(lp.amount_ngwee)::bigint AS fee "
        "FROM public.payments p JOIN public.ledger_transactions lt ON lt.payment_id = p.id "
        "JOIN public.ledger_postings lp ON lp.transaction_id = lt.id "
        "JOIN public.ledger_accounts la ON la.id = lp.account_id "
        "AND la.kind = 'fees' AND la.vendor_id IS NULL "
        "WHERE p.status = 'success' AND p.checkout_group_id IN (SELECT checkout_group_id FROM po) "
        "GROUP BY 1), "
        "ob AS (SELECT po.id AS order_id, po.fulfilment, po.delivery_fee_ngwee, "
        "coalesce((SELECT sum(oi.qty::bigint * oi.unit_price_ngwee)::bigint "
        "FROM public.order_items oi WHERE oi.order_id = po.id), 0) AS items_ngwee, "
        "coalesce((SELECT sum(((l ->> 'line_total_ngwee')::bigint * (l ->> 'rate_bps')::bigint) "
        "/ 10000)::bigint FROM jsonb_array_elements(CASE WHEN "
        "jsonb_typeof(po.commission_snapshot -> 'lines') = 'array' "
        "THEN po.commission_snapshot -> 'lines' ELSE '[]'::jsonb END) l "
        "WHERE l ->> 'line_total_ngwee' ~ '^[0-9]+$' AND l ->> 'rate_bps' ~ '^[0-9]+$'), 0) "
        "AS commission_ngwee, "
        "gf.fee IS NOT NULL AS fee_booked, coalesce(gf.fee, 0) AS group_fee, "
        "coalesce(gv.value, 0) AS group_value, "
        "(SELECT dr.quoted_price_ngwee FROM public.dispatch_requests dr "
        "WHERE dr.order_id = po.id AND dr.status <> 'cancelled' "
        "ORDER BY dr.requested_at DESC, dr.id DESC LIMIT 1) AS courier_ngwee, "
        "coalesce((SELECT sum(r.amount_ngwee)::bigint FROM public.refunds r "
        "WHERE r.order_id = po.id AND r.status = 'completed'), 0) AS refunded_ngwee "
        "FROM po LEFT JOIN gf USING (checkout_group_id) LEFT JOIN gv USING (checkout_group_id)), "
        "oc0 AS (SELECT ob.*, ob.items_ngwee + ob.delivery_fee_ngwee AS order_value, "
        "CASE WHEN ob.group_value > 0 THEN ob.group_fee * (ob.items_ngwee + ob.delivery_fee_ngwee) "
        "/ ob.group_value ELSE 0 END AS payment_fee_ngwee, "
        "coalesce(ob.courier_ngwee, 0) AS courier_cost_ngwee, "
        "(ob.fulfilment = 'delivery' AND ob.courier_ngwee IS NULL) AS courier_unknown FROM ob), "
        "oc1 AS (SELECT oc0.*, CASE WHEN oc0.order_value > 0 AND oc0.refunded_ngwee > 0 THEN "
        "least(oc0.commission_ngwee + oc0.delivery_fee_ngwee, (oc0.commission_ngwee + "
        "oc0.delivery_fee_ngwee) * oc0.refunded_ngwee / oc0.order_value) ELSE 0 END "
        "AS refund_loss_ngwee FROM oc0), "
        "oc AS (SELECT oc1.*, oc1.commission_ngwee + oc1.delivery_fee_ngwee "
        "- oc1.payment_fee_ngwee - oc1.courier_cost_ngwee - oc1.refund_loss_ngwee "
        "AS contribution_ngwee FROM oc1)"
    )


def _base_ctes(window: Window, *, finance: bool) -> str:
    start, end = window.start, window.end
    since = f"({lower_bound(start)} - interval '{CLIP_ATTRIBUTION_DAYS} days')"
    return (
        f"WITH po AS ({_paid_orders(start, end)}), "
        "ol AS (SELECT po.id AS order_id, po.customer_id, po.created_at, oip.listing_id, "
        "oi.qty::bigint AS qty, oi.qty::bigint * oi.unit_price_ngwee AS line_ngwee FROM po "
        "JOIN public.order_items oi ON oi.order_id = po.id "
        "JOIN public.order_item_products oip ON oip.order_item_id = oi.id), "
        f"ca_all AS ({_cart_lines(since, end)}), "
        f"ca AS (SELECT * FROM ca_all WHERE created_at >= {lower_bound(start)}), "
        "dim AS (SELECT vl.id AS listing_id, vl.vendor_id, vl.product_id, p.category_id "
        "FROM public.vendor_listings vl LEFT JOIN public.products p ON p.id = vl.product_id), "
        f"{_contribution_cte(finance=finance)}"
    )


_KEYS: Final[dict[str, str]] = {
    "categories": "d.category_id",
    "products": "d.product_id",
    "vendors": "d.vendor_id",
}

_LABELS: Final[dict[str, str]] = {
    "categories": "(SELECT c.name FROM public.categories c WHERE c.id::text = k.k)",
    "products": "(SELECT p.name FROM public.products p WHERE p.id::text = k.k)",
    "vendors": "(SELECT v.display_name FROM public.vendors v WHERE v.id::text = k.k)",
    "clips": (
        "(SELECT v.display_name || ': ' || coalesce(nullif(left(vc.caption, 48), ''), "
        "left(vc.id::text, 8)) FROM public.video_clips vc JOIN public.vendors v "
        "ON v.id = vc.vendor_id WHERE vc.id::text = k.k)"
    ),
}


def _keyed_sources(grain: Grain, window: Window) -> str:
    """``kv`` (views), ``kc`` (carts) and ``kl`` (order lines), each keyed by ``k``."""
    if grain == "clips":
        days = CLIP_ATTRIBUTION_DAYS
        return (
            "kv AS (SELECT cv.clip_id::text AS k, count(*)::bigint AS v FROM public.clip_views cv "
            f"WHERE cv.viewed_on BETWEEN {_d(window.start)} AND {_d(window.end)} GROUP BY 1), "
            "kc AS (SELECT ca.clip_id::text AS k, count(*)::bigint AS c FROM ca "
            "WHERE ca.clip_id IS NOT NULL GROUP BY 1), "
            "kl AS (SELECT x.k, x.order_id, x.customer_id, x.qty, x.line_ngwee FROM ("
            "SELECT ol.*, (SELECT c.clip_id::text FROM ca_all c WHERE c.clip_id IS NOT NULL "
            "AND c.customer_id = ol.customer_id AND c.listing_id = ol.listing_id "
            f"AND c.created_at <= ol.created_at AND c.created_at > ol.created_at - interval "
            f"'{days} days' ORDER BY c.created_at DESC LIMIT 1) AS k FROM ol) x "
            "WHERE x.k IS NOT NULL)"
        )
    key = _KEYS[grain]
    return (
        f"kv AS (SELECT {key}::text AS k, sum(la.pdp_views)::bigint AS v "
        "FROM public.listing_analytics la JOIN dim d ON d.listing_id = la.listing_id "
        f"WHERE la.day BETWEEN {_d(window.start)} AND {_d(window.end)} GROUP BY 1), "
        f"kc AS (SELECT {key}::text AS k, count(*)::bigint AS c FROM ca "
        "JOIN dim d ON d.listing_id = ca.listing_id GROUP BY 1), "
        f"kl AS (SELECT {key}::text AS k, ol.order_id, ol.customer_id, ol.qty, ol.line_ngwee "
        "FROM ol JOIN dim d ON d.listing_id = ol.listing_id)"
    )


def scorecard_sql(grain: Grain, window: Window, *, finance: bool) -> str:
    return (
        _base_ctes(window, finance=finance) + ", " + _keyed_sources(grain, window) + ", "
        "kt AS (SELECT kl.order_id, sum(kl.line_ngwee)::bigint AS t FROM ol kl GROUP BY 1), "
        "ko AS (SELECT kl.k, count(DISTINCT kl.order_id) AS orders, sum(kl.qty)::bigint AS units, "
        "count(DISTINCT kl.customer_id) AS customers, sum(kl.line_ngwee)::bigint AS items, "
        "sum(CASE WHEN kt.t > 0 THEN oc.contribution_ngwee * kl.line_ngwee / kt.t ELSE 0 END)"
        "::bigint AS contribution FROM kl JOIN kt USING (order_id) JOIN oc USING (order_id) "
        "GROUP BY 1), "
        "kr AS (SELECT r.k, count(*) AS repeat FROM (SELECT kl.k, kl.customer_id FROM kl "
        "GROUP BY 1, 2 HAVING count(DISTINCT kl.order_id) >= 2) r GROUP BY 1), "
        "k AS (SELECT k FROM kv UNION SELECT k FROM kc UNION SELECT k FROM ko) "
        "SELECT k.k, coalesce(kv.v, 0), coalesce(kc.c, 0), coalesce(ko.orders, 0), "
        "coalesce(ko.units, 0), coalesce(ko.customers, 0), coalesce(kr.repeat, 0), "
        "coalesce(ko.items, 0), coalesce(ko.contribution, 0), "
        f"{_clean(_LABELS[grain])} FROM k LEFT JOIN kv USING (k) LEFT JOIN kc USING (k) "
        "LEFT JOIN ko USING (k) LEFT JOIN kr USING (k) WHERE k.k IS NOT NULL;"
    )


@dataclass(frozen=True, slots=True)
class Score:
    key: str
    label: str
    views: int
    carts: int
    orders: int
    units: int
    customers: int
    repeat_customers: int
    items_ngwee: int
    contribution_ngwee: int

    @property
    def view_to_order_bps(self) -> int | None:
        return rate_bps(self.orders, self.views)

    def as_dict(self, *, finance: bool) -> dict[str, Any]:
        return {
            "id": self.key,
            "name": self.label,
            "views": self.views,
            "carts": self.carts,
            "orders": self.orders,
            "units": self.units,
            "customers": self.customers,
            "repeat_customers": self.repeat_customers,
            "view_to_cart_bps": rate_bps(self.carts, self.views),
            "cart_to_order_bps": rate_bps(self.orders, self.carts),
            "view_to_order_bps": self.view_to_order_bps,
            "repeat_rate_bps": rate_bps(self.repeat_customers, self.customers),
            "item_sales_ngwee": self.items_ngwee if finance else None,
            "contribution_ngwee": self.contribution_ngwee if finance else None,
            "contribution_per_order_ngwee": (
                (self.contribution_ngwee // self.orders if self.orders else None)
                if finance
                else None
            ),
        }


def parse_scores(rows: list[list[str]]) -> list[Score]:
    out: list[Score] = []
    for row in rows:
        if len(row) < 10:
            continue
        label = "|".join(row[9:])  # labels are cleaned; join defensively anyway
        values = [int(v) if v not in ("", None) else 0 for v in row[1:9]]
        out.append(Score(row[0], label, *values))
    return out


def rank(scores: list[Score]) -> dict[str, list[Score]]:
    """Top sellers, bottom (attention without sales) and hidden gems."""
    top = sorted(
        (s for s in scores if s.orders > 0),
        key=lambda s: (-s.orders, -s.units, -s.views, s.key),
    )[:LIST_SIZE]
    bottom = sorted(
        (s for s in scores if s.views >= MIN_VIEWS),
        key=lambda s: (s.view_to_order_bps or 0, -s.views, s.key),
    )[:LIST_SIZE]
    gems = sorted(
        (s for s in scores if s.orders >= MIN_ORDERS and s.views > 0),
        key=lambda s: (-(s.view_to_order_bps or 0), s.views, s.key),
    )[:LIST_SIZE]
    return {"top": top, "bottom": bottom, "hidden_gems": gems}


def scorecard(grain: Grain, window: Window, *, finance: bool) -> dict[str, Any]:
    scores = parse_scores(_rows(scorecard_sql(grain, window, finance=finance)))
    ranked = rank(scores)
    return {
        "entities": len(scores),
        **{name: [s.as_dict(finance=finance) for s in items] for name, items in ranked.items()},
    }


def funnel_totals(window: Window) -> dict[str, Any]:
    """Platform funnel: views, carts, paid orders, buyers, repeat and returning buyers."""
    start, end = window.start, window.end
    views, carts, orders, customers, repeat, returning = _ints(
        f"WITH po AS ({_paid_orders(start, end)}), "
        f"ca AS ({_cart_lines(lower_bound(start), end)}) SELECT "
        "(SELECT coalesce(sum(pdp_views), 0)::bigint FROM public.listing_analytics "
        f"WHERE day BETWEEN {_d(start)} AND {_d(end)}), "
        "(SELECT count(*) FROM ca), (SELECT count(*) FROM po), "
        "(SELECT count(DISTINCT customer_id) FROM po), "
        "(SELECT count(*) FROM (SELECT customer_id FROM po GROUP BY 1 "
        "HAVING count(*) >= 2) r), "
        "(SELECT count(DISTINCT po.customer_id) FROM po WHERE EXISTS (SELECT 1 "
        "FROM public.orders o WHERE o.customer_id = po.customer_id AND o.status <> 'cancelled' "
        f"AND o.created_at < {lower_bound(start)} AND EXISTS (SELECT 1 FROM public.payments p "
        "WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success')));",
        6,
    )
    return {
        "views": views,
        "carts": carts,
        "orders": orders,
        "customers": customers,
        "repeat_customers": repeat,
        "returning_customers": returning,
        "view_to_cart_bps": rate_bps(carts, views),
        "cart_to_order_bps": rate_bps(orders, carts),
        "view_to_order_bps": rate_bps(orders, views),
        "repeat_rate_bps": rate_bps(repeat, customers),
        "returning_rate_bps": rate_bps(returning, customers),
    }


CONTRIBUTION_KEYS: Final = (
    "orders",
    "items_ngwee",
    "delivery_fee_ngwee",
    "commission_ngwee",
    "payment_fee_ngwee",
    "courier_cost_ngwee",
    "refunded_ngwee",
    "refund_loss_ngwee",
    "contribution_ngwee",
    "negative_orders",
    "fee_unbooked_orders",
    "courier_cost_unknown_orders",
)


def contribution(window: Window) -> dict[str, Any]:
    """Per-order contribution after payment fee, courier and refunds (finance only)."""
    values = _ints(
        _base_ctes(window, finance=True) + " SELECT count(*), "
        "coalesce(sum(items_ngwee), 0)::bigint, coalesce(sum(delivery_fee_ngwee), 0)::bigint, "
        "coalesce(sum(commission_ngwee), 0)::bigint, coalesce(sum(payment_fee_ngwee), 0)::bigint, "
        "coalesce(sum(courier_cost_ngwee), 0)::bigint, coalesce(sum(refunded_ngwee), 0)::bigint, "
        "coalesce(sum(refund_loss_ngwee), 0)::bigint, "
        "coalesce(sum(contribution_ngwee), 0)::bigint, "
        "count(*) FILTER (WHERE contribution_ngwee < 0), count(*) FILTER (WHERE NOT fee_booked), "
        "count(*) FILTER (WHERE courier_unknown) FROM oc;",
        len(CONTRIBUTION_KEYS),
    )
    out: dict[str, Any] = dict(zip(CONTRIBUTION_KEYS, values, strict=True))
    orders = out["orders"]
    out["contribution_per_order_ngwee"] = out["contribution_ngwee"] // orders if orders else None
    out["margin_bps"] = rate_bps(
        out["contribution_ngwee"], out["items_ngwee"] + out["delivery_fee_ngwee"]
    )
    return out


def build_performance(window: Window, *, include_money: bool) -> dict[str, Any]:
    return {
        "range": window.as_dict(),
        "finance_visible": include_money,
        "thresholds": {
            "min_views": MIN_VIEWS,
            "min_orders": MIN_ORDERS,
            "clip_attribution_days": CLIP_ATTRIBUTION_DAYS,
            "list_size": LIST_SIZE,
        },
        "funnel": funnel_totals(window),
        "contribution": contribution(window) if include_money else None,
        **{grain: scorecard(grain, window, finance=include_money) for grain in GRAINS},
    }
