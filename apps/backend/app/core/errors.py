class DomainError(Exception):
    """业务规则错误，由全局异常处理器转成对应 HTTP 状态码。"""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    """状态冲突，如对已过账的单据再次过账。"""

    status_code = 409
