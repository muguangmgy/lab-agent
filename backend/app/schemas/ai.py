from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    thread_id: str | None = None

    @field_validator("thread_id", mode="before")
    @classmethod
    def empty_thread_as_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ChatReply(BaseModel):
    role: str
    content: str
    thread_id: str


class SessionItem(BaseModel):
    thread_id: str
    title: str
    create_time: str | None = None
    update_time: str | None = None

    model_config = {"from_attributes": True}


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1)
