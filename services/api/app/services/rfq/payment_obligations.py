"""Protected read model for service funding; collection RPCs own all mutations."""

from typing import Any

from app.schemas.base import StrictModel


class ServiceObligationOut(StrictModel):
    id: str
    job_id: str
    order_id: str
    checkout_group_id: str
    leg: str
    amount_ngwee: int
    status: str
    payment_id: str | None
    can_pay: bool


def list_service_obligations(client: Any, *, order_id: str) -> list[ServiceObligationOut]:
    order_response = client.table("orders").select("status").eq("id", order_id).single().execute()
    order = order_response.data
    obligations = (
        client.table("service_payment_obligations")
        .select("*")
        .eq("order_id", order_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    result = []
    acknowledgement: dict[str, bool] = {}
    for ob in obligations:
        group = (
            client.table("checkout_groups")
            .select("status")
            .eq("id", ob["checkout_group_id"])
            .single()
            .execute()
            .data
        )
        payments = (
            client.table("payments")
            .select("id,status,raw,lenco_reference,provider,rail,amount_ngwee")
            .eq("checkout_group_id", ob["checkout_group_id"])
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        paid = False
        for payment in payments:
            receipts = (
                client.table("payment_collection_receipts")
                .select("receipt_identity,canonical_status_verified_at")
                .eq("payment_id", payment["id"])
                .execute()
                .data
                or []
            )
            paid = paid or any(
                r["receipt_identity"].get("merchant_reference") == payment["lenco_reference"]
                and r["receipt_identity"].get("provider") == payment["provider"]
                and r["receipt_identity"].get("currency") == "ZMW"
                and (payment["rail"] != "card" or r.get("canonical_status_verified_at") is not None)
                and r["receipt_identity"].get("amount_ngwee") == ob["amount_ngwee"]
                for r in receipts
            )
        latest = payments[0] if payments else None
        if ob["job_id"] not in acknowledgement:
            acknowledgement[ob["job_id"]] = (
                client.rpc("service_buyer_acknowledged", {"p_job_id": ob["job_id"]})
                .execute().data is True
            )
        ready = ob["leg"] == "deposit" or (
            ob["work_acknowledged_at"] is not None and acknowledgement[ob["job_id"]]
        )
        status = "paid" if paid else (str(latest["status"]) if latest else "unpaid")
        result.append(
            ServiceObligationOut(
                id=ob["id"],
                job_id=ob["job_id"],
                order_id=order_id,
                checkout_group_id=ob["checkout_group_id"],
                leg=ob["leg"],
                amount_ngwee=ob["amount_ngwee"],
                status=status,
                payment_id=latest["id"] if latest else None,
                can_pay=not paid
                and ready
                and order["status"] == "placed"
                and group["status"] == "pending"
                and (
                    latest is None
                    or (
                        latest["status"] == "failed"
                        and latest.get("raw", {}).get("terminal_provider_failure") is True
                    )
                ),
            )
        )
    return result
