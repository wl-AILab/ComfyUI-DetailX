class DetailXError(Exception):
    def __init__(self, message: str, *, code: str = "detailx_error", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class BudgetExceeded(DetailXError):
    def __init__(self, credits: int, budget: int):
        super().__init__(f"Quote {credits} credits exceeds precharge budget {budget}.", code="budget_exceeded")


class OperationStopped(DetailXError):
    def __init__(self):
        super().__init__("Local operation stopped. An accepted generation continues on the server.", code="stopped")
