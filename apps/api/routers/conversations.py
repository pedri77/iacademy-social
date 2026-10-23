"""Authorized commercial metadata for a single inbound Meta message.

Message contents and platform-user identities stay in BrightBean. A contact
may legitimately have several identities after a merge; none is guessed here.
"""

from typing import Any
from uuid import UUID

from django.http import Http404
from django.urls import reverse
from ninja import Query, Router

from apps.api.requests import ApiRequest
from apps.api.schemas import ConversationContextOut
from apps.common.platforms import Platform
from apps.common.shortcuts import get_scoped_object_or_404
from apps.contacts.models import ContactStatus
from apps.members.decorators import require_permission
from apps.messaging.models import (
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)

__all__ = ["router"]

router = Router(tags=["conversations"])
_MESSAGE_ID_QUERY = Query(...)

#: The platforms this endpoint serves. Deliberately not every platform the
#: product speaks: the consumer of this context is the Meta centralisation
#: integration, and answering 404 for the rest keeps the endpoint's meaning
#: ("what the customer said on Meta") honest while that is true.
META_PLATFORMS: frozenset[str] = frozenset({Platform.INSTAGRAM.value, Platform.MESSENGER.value})


#: The only attribution keys this endpoint will ever return. Anything else a
#: message body carries is dropped, not passed through.
ATTRIBUTION_KEYS: tuple[str, ...] = ("campaign_id", "ad_id", "media_id", "comment_id", "ref")

#: Cap on one attribution value. These are ids and ref strings, not prose.
MAX_ATTRIBUTION_CHARS = 200


def _attribution_of(message: Message) -> dict[str, str]:
    """The allowlisted attribution keys present on the body, capped.

    Inbound bodies carry ``ref`` (and a comment id on a private reply) — but
    this reads the body rather than hard-coding that, so a future attribution
    key lands by adding it to :data:`ATTRIBUTION_KEYS` and nowhere else.
    Non-string and empty values are dropped rather than stringified: an
    attribution key is an id, and ``"None"`` is a lie about provenance.
    """
    if not isinstance(message.body, dict):
        return {}
    found: dict[str, str] = {}
    for key in ATTRIBUTION_KEYS:
        value = message.body.get(key)
        if isinstance(value, str) and value:
            found[key] = value[:MAX_ATTRIBUTION_CHARS]
    return found


@router.get(
    "/conversations/{uuid:conversation_id}/context",
    response=ConversationContextOut,
    url_name="conversations_context",
)
@require_permission("use_inbox")
def conversation_context(
    request: ApiRequest,
    conversation_id: UUID,
    message_id: UUID = _MESSAGE_ID_QUERY,
) -> dict[str, Any]:
    """Context for one inbound message's thread, for an authenticated connector.

    ``message_id`` is a query parameter rather than a path segment because the
    message names *which moment* of the thread is being asked about; the thread
    is the object. A message that is not an inbound, non-internal, non-deleted
    row of this conversation is a 404 — indistinguishable from another
    workspace's ids (SECURITY-BASELINE §1).
    """
    conversation = get_scoped_object_or_404(Conversation, request.workspace, pk=conversation_id)
    contact = conversation.contact
    connection = conversation.channel_connection

    # Every refusal below is a 404, on purpose: the caller's key names their
    # workspace, so "not yours" and "not there" must read identically.
    if contact.status != ContactStatus.ACTIVE:
        raise Http404("No Conversation matches the given query.") from None
    if connection.platform not in META_PLATFORMS:
        raise Http404("No Conversation matches the given query.") from None

    message = get_scoped_object_or_404(Message, request.workspace, pk=message_id, conversation=conversation)
    if message.direction != MessageDirection.IN or message.internal or message.status == MessageStatus.DELETED:
        raise Http404("No Conversation matches the given query.") from None

    return {
        "version": 1,
        "workspace_id": request.workspace.pk,
        "contact": {
            "id": contact.pk,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "status": contact.status,
        },
        "connection": {
            "id": connection.pk,
            "platform": connection.platform,
            "platform_account_id": connection.external_id,
        },
        "conversation": {
            "id": conversation.pk,
            "state": conversation.state,
            # Reversed from this deployment's URL conf, never from anything
            # the caller or the platform supplied.
            "path": reverse(
                "inbox:thread",
                kwargs={"workspace_id": request.workspace.pk, "conversation_id": conversation.pk},
            ),
        },
        "message": {
            "id": message.pk,
            "provider_message_id": message.provider_message_id,
            "direction": message.direction,
            "status": message.status,
            "created_at": message.created_at,
        },
        "attribution": _attribution_of(message),
    }
