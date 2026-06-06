from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AddAccountRequest(BaseModel):
    label: str = Field(default="", max_length=120)
    token: str = Field(min_length=1)
    storage: Literal["keyring", "memory"] = "keyring"


class PathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


class UploadResult(BaseModel):
    history: dict
    metadata: dict

