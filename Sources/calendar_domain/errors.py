"""Stable domain errors that hide SQLite and filesystem details."""


class DomainError(Exception):
    """Base error for callers of the CAL domain interface."""


class NotFoundError(DomainError):
    """A requested CAL entity or authoritative Trip does not exist."""


class ValidationError(DomainError):
    """A command or authoritative source does not satisfy the CAL contract."""


class ConflictError(DomainError):
    """A command conflicts with current state or source authority."""


class GenerationWriteError(DomainError):
    """A generation promotion could not be persisted; no terminal result is implied."""
