from typing import Any, Optional

from pydantic import BaseModel, Field

class BaseSchema(BaseModel):
    """Base Pydantic schema with common config."""
    
    class Config:
        extra = "allow"
        validate_assignment = True


class ToolInput(BaseSchema):
    """Base schema for tool inputs."""
    pass


class ToolOutput(BaseSchema):
    """Base schema for tool outputs."""
    success: bool = True
    error: Optional[str] = None
    data: Any = None


class AgentConfig(BaseSchema):
    """Configuration for an agent."""
    name: str = Field(default="agent", description="Agent name")
    description: str = Field(default="", description="Agent description")
    max_iterations: int = Field(default=10, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


__all__ = [
    "BaseSchema",
    "ToolInput",
    "ToolOutput",
    "AgentConfig",
]
