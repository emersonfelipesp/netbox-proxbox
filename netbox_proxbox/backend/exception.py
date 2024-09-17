from netbox_proxbox.backend.logging import logger

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
        
        log_message=f"ProxboxException: {self.message}"
        
        if self.detail:
            log_message+=f"\n > Detail: {self.detail}"
        
        if self.python_exception:
            log_message+=f"\n > Python Exception: {self.python_exception}"
            
        
        logger.error(log_message)
        
        