"""Tests for best-effort n8n webhook dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
from app.services.webhooks.n8n_dispatch import (
    build_n8n_payload,
    post_n8n_webhook,
    schedule_n8n_webhook,
)
from app.settings import Settings
from fastapi import BackgroundTasks


def test_build_n8n_payload_merges_event_and_data() -> None:
    payload = build_n8n_payload(
        event="order.created",
        data={"order_id": "ord-1", "items": []},
    )
    assert payload["event"] == "order.created"
    assert payload["order_id"] == "ord-1"


def test_post_n8n_webhook_noop_when_url_unset() -> None:
    settings = Settings(
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="dev",
        SUPABASE_ANON_KEY="dev",
        N8N_WEBHOOK_URL="",
    )
    with patch("app.services.webhooks.n8n_dispatch.httpx.Client") as client_cls:
        post_n8n_webhook({"event": "order.created"}, settings=settings)
        client_cls.assert_not_called()


def test_post_n8n_webhook_swallows_http_errors() -> None:
    settings = Settings(
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="dev",
        SUPABASE_ANON_KEY="dev",
        N8N_WEBHOOK_URL="https://n8n.example/webhook/test",
    )
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("app.services.webhooks.n8n_dispatch.httpx.Client", return_value=mock_client):
        post_n8n_webhook({"event": "order.created"}, settings=settings)


def test_post_n8n_webhook_posts_json_when_configured() -> None:
    settings = Settings(
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="dev",
        SUPABASE_ANON_KEY="dev",
        N8N_WEBHOOK_URL="https://n8n.example/webhook/test",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    payload = {"event": "order.created", "order_id": "ord-abc"}
    with patch("app.services.webhooks.n8n_dispatch.httpx.Client", return_value=mock_client):
        post_n8n_webhook(payload, settings=settings)

    mock_client.post.assert_called_once_with(
        "https://n8n.example/webhook/test",
        json=payload,
    )


def test_schedule_n8n_webhook_registers_background_task() -> None:
    settings = Settings(
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="dev",
        SUPABASE_ANON_KEY="dev",
        N8N_WEBHOOK_URL="https://n8n.example/webhook/test",
    )
    tasks = BackgroundTasks()
    schedule_n8n_webhook(
        tasks,
        event="order.created",
        data={"order_id": "ord-1"},
        settings=settings,
    )
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is post_n8n_webhook
