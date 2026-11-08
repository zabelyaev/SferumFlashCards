class UnauthorizedError(Exception):
    def __init__(self, detail: str = "Authentication required.") -> None:
        self.detail = detail
        super().__init__(detail)
