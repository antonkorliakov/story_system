class AppError(Exception):
    """An application failure that can be safely serialized for API clients."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = {} if details is None else details
