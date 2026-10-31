"""Strict public result validation, shared by simulation and evaluation owners."""
from pydantic import BaseModel, ConfigDict


class StrictResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
