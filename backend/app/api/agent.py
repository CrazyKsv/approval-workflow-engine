from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import orchestrator
from app.db import get_db
from app.deps import get_current_user
from app.exceptions import NotFoundError, PermissionDeniedError
from app.models import AgentConversation, User
from app.pagination import PageParams, paginate
from app.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversationDetailOut,
    AgentConversationOut,
    Page,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return orchestrator.chat(db, user, payload.message, payload.conversation_id)


@router.get("/conversations", response_model=Page[AgentConversationOut])
def list_conversations(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(AgentConversation)
        .where(AgentConversation.user_id == user.id)
        .order_by(AgentConversation.updated_at.desc())
    )
    items, total = paginate(db, query, params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/conversations/{conversation_id}", response_model=AgentConversationDetailOut)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full observable trace: user messages, assistant steps, tool invocations."""
    conversation = db.get(AgentConversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.user_id != user.id and user.role != "admin":
        raise PermissionDeniedError("This conversation belongs to another user")
    return conversation
