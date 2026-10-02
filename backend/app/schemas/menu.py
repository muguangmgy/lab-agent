from pydantic import BaseModel, ConfigDict, Field


class MenuResponse(BaseModel):
    id: int
    parent_id: int | None = None
    name: str
    type: str
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission: str | None = None
    sort: int = 0
    visible: int = 1
    status: int = 1
    children: list["MenuResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MenuCreateRequest(BaseModel):
    parent_id: int | None = None
    name: str
    type: str = "menu"
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission: str | None = None
    sort: int = 0
    visible: int = 1
    status: int = 1


class MenuUpdateRequest(BaseModel):
    parent_id: int | None = None
    name: str | None = None
    type: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission: str | None = None
    sort: int | None = None
    visible: int | None = None
    status: int | None = None


MenuResponse.model_rebuild()
