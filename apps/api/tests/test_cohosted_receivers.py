"""An operator-approved webhook may share the deployment's public proxy IP."""

import uuid

import httpx
import pytest

from apps.api.delivery import enqueue_delivery
from apps.api.models import DeliveryStatus, WebhookDelivery
from apps.api.tests.support import PUBLIC, RECEIVER, FakeInternet, drain_webhook_deliveries, serving
from apps.common.outbound import reset_deployment_cache
from apps.common.signing import webhook_signature_matches

APP_HOST = "chat.example.com"


@pytest.fixture
def cohosted(tenancy, webhook, settings):
    settings.APP_URL = f"https://{APP_HOST}"
    settings.ALLOWED_HOSTS = [APP_HOST]
    settings.API_WEBHOOK_COHOSTED_RECEIVERS = {str(tenancy.workspace.id): [webhook.url]}
    reset_deployment_cache()
    yield
    reset_deployment_cache()


def deliver(tenancy, webhook):
    enqueue_delivery(webhook, event="contact.created", data={"contact_id": "c1"})
    drain_webhook_deliveries(tenancy.workspace)
    return WebhookDelivery.objects.for_workspace(tenancy.workspace).get()


@pytest.mark.django_db
class TestCohostedReceivers:
    def test_approved_receiver_gets_signed_delivery_on_shared_public_address(
        self, tenancy, webhook, cohosted, monkeypatch
    ):
        internet = FakeInternet(serving(200), names={APP_HOST: [PUBLIC], RECEIVER: [PUBLIC]}).install(monkeypatch)
        result = deliver(tenancy, webhook)

        assert result.status == DeliveryStatus.SUCCEEDED
        assert result.response_code == 200
        sent = internet.requests[0]
        assert sent.url.host == PUBLIC
        assert sent.headers["host"] == RECEIVER
        assert webhook_signature_matches(
            webhook.secret,
            timestamp=int(sent.headers["X-BrightBean-Timestamp"]),
            raw_body=sent.content,
            presented=sent.headers["X-BrightBean-Signature"],
        )

    @pytest.mark.parametrize("scope", ["disabled", "other_workspace", "other_path", "other_port"])
    def test_approval_does_not_extend_to_another_workspace_or_url(
        self, scope, tenancy, webhook, cohosted, settings, monkeypatch
    ):
        if scope == "disabled":
            settings.API_WEBHOOK_COHOSTED_RECEIVERS = {}
        elif scope == "other_workspace":
            settings.API_WEBHOOK_COHOSTED_RECEIVERS = {str(uuid.uuid4()): [webhook.url]}
        elif scope == "other_path":
            webhook.url += "/other"
            webhook.save(update_fields=["url"])
        else:
            webhook.url = f"https://{RECEIVER}:8443/hooks"
            webhook.save(update_fields=["url"])
        internet = FakeInternet(serving(200), names={APP_HOST: [PUBLIC], RECEIVER: [PUBLIC]}).install(monkeypatch)

        assert deliver(tenancy, webhook).status == DeliveryStatus.BLOCKED
        assert internet.requests == []

    @pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.5"], ["169.254.169.254"], [PUBLIC, "::1"]])
    @pytest.mark.parametrize("allow_private", [False, True])
    def test_even_approved_receiver_cannot_reach_private_or_mixed_dns(
        self, addresses, allow_private, tenancy, webhook, cohosted, settings, monkeypatch
    ):
        settings.EXTERNAL_REQUEST_ALLOW_PRIVATE = allow_private
        internet = FakeInternet(serving(200), names={APP_HOST: [PUBLIC], RECEIVER: addresses}).install(monkeypatch)

        assert deliver(tenancy, webhook).status == DeliveryStatus.BLOCKED
        assert internet.requests == []

    @pytest.mark.parametrize(
        "url",
        [
            f"http://{RECEIVER}/hooks",
            f"https://{RECEIVER}/hooks?target=other",
            f"https://{RECEIVER}/hooks#fragment",
            f"https://{APP_HOST}/internal",
            f"https://{PUBLIC}/hooks",
            f"https://user:password@{RECEIVER}/hooks",
        ],
    )
    def test_invalid_operator_approval_does_not_weaken_scheme_identity_or_credentials(
        self, url, tenancy, webhook, cohosted, settings, monkeypatch
    ):
        webhook.url = url
        webhook.save(update_fields=["url"])
        settings.API_WEBHOOK_COHOSTED_RECEIVERS = {str(tenancy.workspace.id): [url]}
        internet = FakeInternet(serving(200), names={APP_HOST: [PUBLIC], RECEIVER: [PUBLIC], PUBLIC: [PUBLIC]}).install(
            monkeypatch
        )

        assert deliver(tenancy, webhook).status == DeliveryStatus.BLOCKED
        assert internet.requests == []

    @pytest.mark.parametrize("destination", ["/another-path", "https://elsewhere.example.com/collect"])
    def test_approved_receiver_cannot_redirect_signed_payload(
        self, destination, tenancy, webhook, cohosted, monkeypatch
    ):
        calls = []

        def redirect(request):
            calls.append(str(request.url))
            return httpx.Response(307, headers={"Location": destination})

        internet = FakeInternet(
            redirect, names={APP_HOST: [PUBLIC], RECEIVER: [PUBLIC], "elsewhere.example.com": ["8.8.8.8"]}
        ).install(monkeypatch)

        assert deliver(tenancy, webhook).status == DeliveryStatus.BLOCKED
        assert len(calls) == 1
        assert internet.requests[0].headers["host"] == RECEIVER
