from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
from georisk.pipeline.context import StepContext

class ErrorPolicy(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"

@dataclass
class StepResult:
    success: bool
    message: str = ""
    error: Exception | None = None
    skipped: bool = False
    skip_reason: str = ""

class PipelineStep(ABC):
    name: str
    error_policy: ErrorPolicy

    @abstractmethod
    def execute(self, ctx: "StepContext") -> StepResult:
        pass

    def should_skip(self, ctx: "StepContext") -> str | None:
        return None