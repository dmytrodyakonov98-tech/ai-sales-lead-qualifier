from pydantic import BaseModel, ConfigDict, Field


class DraftLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)
