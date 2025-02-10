import logging
from logging.handlers import TimedRotatingFileHandler
from fastapi import WebSocket

# ANSI escape sequences for colors
class AnsiColorCodes:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    RESET = '\033[0m'
    DARK_GRAY = '\033[90m'

class ColorizedFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: AnsiColorCodes.BLUE,
        logging.INFO: AnsiColorCodes.GREEN,
        logging.WARNING: AnsiColorCodes.YELLOW,
        logging.ERROR: AnsiColorCodes.RED,
        logging.CRITICAL: AnsiColorCodes.MAGENTA
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, AnsiColorCodes.WHITE)
        
        record.module = f"{AnsiColorCodes.DARK_GRAY}{record.module}{AnsiColorCodes.RESET}"

        record.levelname = f"{color}{record.levelname}{AnsiColorCodes.RESET}"
        return super().format(record)

def setup_logger():
    # Path to log file
    log_path = '/var/log/proxbox.log'

    # Create a logger
    logger = logging.getLogger('proxbox')

    logger.setLevel(logging.DEBUG)

    # # Create a console handler
    console_handler = logging.StreamHandler()

    # Log all messages in the console
    console_handler.setLevel(logging.DEBUG)

    # Create a formatter with colors
    formatter = ColorizedFormatter('%(name)s [%(asctime)s] [%(levelname)-8s] %(module)s: %(message)s')
    #formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(module)s: %(message)s')
    # Set the formatter for the console handler and file handler
    console_handler.setFormatter(formatter)

    try:
        # Create a file handler
        file_handler = TimedRotatingFileHandler(log_path, when='midnight', interval=1, backupCount=7)

        # Log only WARNINGS and above in the file
        file_handler.setLevel(logging.WARNING)

        # Set the formatter for the file handler
        file_handler.setFormatter(formatter)
    except:
        print("Not able to create '/var/log/proxbox.log' archive.")

    # Add the handlers to the logger
    logger.addHandler(console_handler)
    # logger.addHandler(file_handler)
    
    logger.propagate = False
    
    return logger


logger = setup_logger()

async def log(websocket: WebSocket, msg, level = None):
    if websocket: 
        await websocket.send_text(msg)
    
    if level == "debug":
        logger.debug(msg)
    
    if level == "ERROR" or level == "error":
        logger.error(msg)
        
    else:
        logger.info(msg)