from typing import Callable
from georisk.pipeline.step import PipelineStep, StepResult, ErrorPolicy
from georisk.pipeline.context import StepContext


class PipelineError(Exception):
    pass

class PipelineOrchestrator:
    def __init__(self, steps: list[PipelineStep], on_progress: Callable[[str, str, str], None] | None = None):
        self.steps = steps
        self.on_progress = on_progress

    def run(self, ctx: StepContext) -> list[StepResult]:
        results = []
        for step in self.steps:
            skip_reason = step.should_skip(ctx)
            if skip_reason:
                result = StepResult(success=True, skipped=True, skip_reason=skip_reason)
                results.append(result)
                if self.on_progress:
                    self.on_progress(step.name, "skipped", skip_reason)
                continue

            try:
                result = step.execute(ctx)
                results.append(result)
                status = "success" if result.success else "failed"
                if self.on_progress:
                    self.on_progress(step.name, status, result.message)
                if not result.success and step.error_policy == ErrorPolicy.REQUIRED:
                    raise PipelineError(f"Step '{step.name}' failed: {result.message}")
            except PipelineError:
                raise
            except Exception as e:
                error_message = f"Exception in step '{step.name}': {str(e)}"
                results.append(StepResult(success=False, message=error_message, error=e))
                if self.on_progress:
                    self.on_progress(step.name, "error", error_message)
                if step.error_policy == ErrorPolicy.REQUIRED:
                    raise PipelineError(error_message) from e

        return results