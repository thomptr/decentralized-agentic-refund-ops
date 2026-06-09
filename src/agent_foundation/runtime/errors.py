from __future__ import annotations


class TaskRejected(Exception):
    """Raised to signal that a task should be rejected."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class UnsupportedCapability(TaskRejected):
    def __init__(self, capability_id: str) -> None:
        super().__init__(
            "unsupported_capability",
            f"Capability {capability_id!r} is not supported by this agent",
        )
        self.capability_id = capability_id


class DuplicateTask(TaskRejected):
    def __init__(self, task_id: str) -> None:
        super().__init__("duplicate", f"Task {task_id!r} has already been processed")
        self.task_id = task_id


class UnknownTask(Exception):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"No result found for task_id={task_id!r}")
        self.task_id = task_id
