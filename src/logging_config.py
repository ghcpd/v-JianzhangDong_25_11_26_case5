import logging
from pythonjsonlogger import jsonlogger


def configure_logging(level=logging.INFO):
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(level)
    # Prevent logs from being duplicated
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    return root
