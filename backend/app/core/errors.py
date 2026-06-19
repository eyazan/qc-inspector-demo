"""Consistent error shape (Section 5): {status, stage, message, details}."""

from app.core.constants import STAGES


class PipelineStageError(Exception):
    """Raised with the pipeline stage where it occurred, for a structured response."""

    def __init__(self, stage: str, message: str, details: dict | None = None):
        if stage not in STAGES:
            stage = "spec_lookup"  # safe default rather than an unknown stage
        self.stage = stage
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return error_payload(self.stage, self.message, self.details)


def error_payload(stage: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "error",
        "stage": stage,
        "message": message,
        "details": details or {},
    }
