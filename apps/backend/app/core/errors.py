class DomainError(Exception):
    """Business rule violation, converted to the matching HTTP status code by the global exception handler."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    """State conflict, e.g. posting an already posted document."""

    status_code = 409
