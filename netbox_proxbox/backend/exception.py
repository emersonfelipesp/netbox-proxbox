from netbox_proxbox import logger

class ProxboxException(Exception):
    def __init__(
        self,
        message: str,
        detail: str | None = None,
        python_exception: str | None = None,
    ):
        self.message = message
        self.detail = detail
        self.python_exception = python_exception
        
        logger.error(f"ProxboxException: {self.message} | Detail: {self.detail}")
        
        