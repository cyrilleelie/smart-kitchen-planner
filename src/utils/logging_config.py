import logging
import sys


def setup_logging(level=logging.INFO, log_file="smartretail.log"):
    """
    Configure logging for the application.

    Args:
        level: Logging level (default: logging.INFO)
        log_file: Path to log file (default: smartretail.log)
    """
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create handlers
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=[stream_handler, file_handler],
        force=True,  # Force reconfiguration
    )

    # Set level for libraries to avoid noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
