class ForbiddenError(Exception):
    def __init__(self, detail: str = "Access denied.") -> None:
        self.detail = detail
        super().__init__(detail)
