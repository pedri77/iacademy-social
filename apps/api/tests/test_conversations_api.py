"""Commercial context: authorization, tenant isolation and data minimization."""

import datetime as dt
from uuid import uuid4

import pytest
from django.urls import reverse

from apps.api.tests.conftest import bearer, make_key
from apps.contacts.models import Contact, ContactStatus
from apps.messaging.models import (
    ContactChannelIdentity,
    Conversation,
    Message,
    MessageDirection,
    MessageSource,
    MessageStatus,
    OptInSource,
)
from tests.support import make_connection

META_PLATFORM = "messenger"


def context_path(conversation, message) -> str:
    return f"/api/v1/conversations/{conversation.pk}/context?message_id={message.pk}"


def make_thread(
    workspace,
    *,
    platform=META_PLATFORM,
    contact_status=ContactStatus.ACTIVE,
    text="¿Me pasáis el temario del módulo 2?",
    body=None,
    direction=MessageDirection.IN,
    internal=False,
    status=MessageStatus.DELIVERED,
    with_identity=True,
):
    """One messenger thread, inbound message and identity, in `workspace`."""
    contact = Contact.objects.create(
        workspace=workspace,
        first_name="Ana",
        last_name="Ruiz",
        email="ana@example.com",
        phone="+34600000000",
        status=contact_status,
    )
    connection = make_connection(workspace, platform=platform, suffix=str(uuid4())[:8])
    conversation = Conversation.objects.create(contact=contact, channel_connection=connection)
    if with_identity:
        identity = ContactChannelIdentity(
            contact=contact,
            channel_connection=connection,
            platform=platform,
            platform_user_id="PSID-1",
            opt_in=True,
            opt_in_at=dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
            opt_in_source=OptInSource.MESSAGE_IN,
        )
        identity.save()
    message = Message.objects.create(
        conversation=conversation,
        direction=direction,
        source="" if direction == MessageDirection.IN else MessageSource.AGENT,
        internal=internal,
        status=status,
        provider_message_id="mid.abc",
        body=body if body is not None else {"blocks": [{"type": "text", "text": text}], "ref": "curso-ia"},
    )
    return contact, connection, conversation, message


@pytest.mark.django_db
class TestConversationContextAuth:
    def test_no_key_is_a_401(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace)
        response = client.get(context_path(conversation, message))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    def test_a_key_without_the_permission_is_a_403(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=())
        response = client.get(context_path(conversation, message), **bearer(plaintext))
        assert response.status_code == 403

    def test_a_read_scope_key_gets_the_payload(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(context_path(conversation, message), **bearer(plaintext))
        assert response.status_code == 200


@pytest.mark.django_db
class TestConversationContextIsolation:
    def test_another_workspaces_conversation_is_a_plain_404(self, client, tenancy, other_tenancy):
        _, _, conversation, message = make_thread(other_tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(context_path(conversation, message), **bearer(plaintext))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_another_workspaces_message_on_our_conversation_is_a_404(self, client, tenancy, other_tenancy):
        _, _, conversation, _ = make_thread(tenancy.workspace)
        _, _, _, foreign_message = make_thread(other_tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(
            f"/api/v1/conversations/{conversation.pk}/context?message_id={foreign_message.pk}",
            **bearer(plaintext),
        )
        assert response.status_code == 404

    def test_a_malformed_conversation_uuid_is_a_404(self, client, tenancy):
        _, _, _, message = make_thread(tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(
            f"/api/v1/conversations/not-a-uuid/context?message_id={message.pk}",
            **bearer(plaintext),
        )
        assert response.status_code == 404

    def test_a_malformed_message_uuid_is_a_422(self, client, tenancy):
        _, _, conversation, _ = make_thread(tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(
            f"/api/v1/conversations/{conversation.pk}/context?message_id=not-a-uuid",
            **bearer(plaintext),
        )
        assert response.status_code == 422

    def test_a_missing_message_id_is_a_422(self, client, tenancy):
        _, _, conversation, _ = make_thread(tenancy.workspace)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(f"/api/v1/conversations/{conversation.pk}/context", **bearer(plaintext))
        assert response.status_code == 422


@pytest.mark.django_db
class TestConversationContextEligibility:
    def _get(self, client, tenancy, conversation, message):
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        return client.get(context_path(conversation, message), **bearer(plaintext))

    def test_a_message_from_another_conversation_is_a_404(self, client, tenancy):
        # Same workspace, same contact shape — a different thread.
        _, _, conversation, _ = make_thread(tenancy.workspace)
        _, _, _, other_message = make_thread(tenancy.workspace)
        assert self._get(client, tenancy, conversation, other_message).status_code == 404

    def test_an_internal_note_is_a_404(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace, internal=True)
        assert self._get(client, tenancy, conversation, message).status_code == 404

    def test_a_deleted_message_is_a_404(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace, status=MessageStatus.DELETED)
        assert self._get(client, tenancy, conversation, message).status_code == 404

    def test_an_outbound_message_is_a_404(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace, direction=MessageDirection.OUT)
        assert self._get(client, tenancy, conversation, message).status_code == 404

    def test_a_non_meta_platform_is_a_404(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace, platform="telegram")
        assert self._get(client, tenancy, conversation, message).status_code == 404

    def test_a_deleted_contact_is_a_404(self, client, tenancy):
        _, _, conversation, message = make_thread(tenancy.workspace, contact_status=ContactStatus.DELETED)
        assert self._get(client, tenancy, conversation, message).status_code == 404

    @pytest.mark.parametrize("identity_count", [0, 2])
    def test_contact_with_zero_or_multiple_identities_keeps_commercial_context(self, client, tenancy, identity_count):
        contact, connection, conversation, message = make_thread(tenancy.workspace, with_identity=False)
        for index in range(identity_count):
            ContactChannelIdentity.objects.create(
                contact=contact,
                channel_connection=connection,
                platform=META_PLATFORM,
                platform_user_id=f"merged-psid-{index}",
            )
        response = self._get(client, tenancy, conversation, message)
        assert response.status_code == 200
        assert response.json()["contact"]["id"] == str(contact.pk)
        assert "identity" not in response.json()


@pytest.mark.django_db
class TestConversationContextPayload:
    def _payload(self, client, tenancy, **thread_kwargs):
        _, connection, conversation, message = make_thread(tenancy.workspace, **thread_kwargs)
        _, plaintext = make_key(tenancy.workspace, scopes=("read",))
        response = client.get(context_path(conversation, message), **bearer(plaintext))
        assert response.status_code == 200
        return conversation, response.json()

    def test_the_real_payload_matches_the_contract(self, client, tenancy):
        conversation, payload = self._payload(client, tenancy)

        assert set(payload) == {
            "version",
            "workspace_id",
            "contact",
            "connection",
            "conversation",
            "message",
            "attribution",
        }
        assert payload["version"] == 1
        assert payload["workspace_id"] == str(tenancy.workspace.pk)

        assert payload["contact"] == {
            "id": str(conversation.contact_id),
            "first_name": "Ana",
            "last_name": "Ruiz",
            "status": "active",
        }

        assert payload["connection"] == {
            "id": str(conversation.channel_connection_id),
            "platform": META_PLATFORM,
            "platform_account_id": conversation.channel_connection.external_id,
        }

        assert set(payload["conversation"]) == {"id", "state", "path"}
        assert payload["conversation"]["id"] == str(conversation.pk)
        assert payload["conversation"]["state"] == "open"
        # The path is the URL conf's own thread route, not anything echoed.
        assert payload["conversation"]["path"] == reverse(
            "inbox:thread",
            kwargs={"workspace_id": tenancy.workspace.pk, "conversation_id": conversation.pk},
        )

        assert set(payload["message"]) == {
            "id",
            "provider_message_id",
            "direction",
            "status",
            "created_at",
        }
        assert payload["message"]["direction"] == "in"
        assert payload["message"]["provider_message_id"] == "mid.abc"
        assert payload["message"]["status"] == "delivered"

        assert payload["attribution"] == {"ref": "curso-ia"}

    def test_no_private_field_ever_leaves_the_payload(self, client, tenancy):
        """The contact row holds an email and a phone; neither may appear."""
        _, payload = self._payload(client, tenancy)
        rendered = repr(payload)
        assert "ana@example.com" not in rendered
        assert "+34600000000" not in rendered
        assert "¿Me pasáis" not in rendered
        assert "PSID-1" not in rendered

    def test_attachments_and_unknown_attribution_keys_are_dropped(self, client, tenancy):
        body = {
            "blocks": [
                {"type": "file", "url": "https://cdn.example.com/x.jpg", "caption": ""},
                {"type": "text", "text": "mira"},
            ],
            "ref": "r" * 500,
            "campaign_id": "camp-1",
            "ad_id": "ad-9",
            "evil_key": "dropped",
            "media_id": 12345,  # non-string: dropped, not stringified
        }
        _, payload = self._payload(client, tenancy, body=body)
        assert "https://cdn.example.com/x.jpg" not in repr(payload)
        assert payload["attribution"] == {"campaign_id": "camp-1", "ad_id": "ad-9", "ref": "r" * 200}
