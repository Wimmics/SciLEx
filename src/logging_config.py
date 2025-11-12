"""
Centralized logging configuration for SciLEx.

This module provides:
1. Environment-variable controlled log levels (LOG_LEVEL)
2. Optional colored output (LOG_COLOR=true)
3. Progress tracking helpers
4. Structured logging utilities

Usage:
    from src.logging_config import setup_logging, get_logger

    # In main script
    setup_logging()

    # In modules
    logger = get_logger(__name__)
    logger.info("Message")
"""

import logging
import os
import sys


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output"""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Levels
    DEBUG = "\033[36m"  # Cyan
    INFO = "\033[32m"  # Green
    WARNING = "\033[33m"  # Yellow
    ERROR = "\033[31m"  # Red
    CRITICAL = "\033[35m"  # Magenta

    # Components
    API = "\033[94m"  # Light blue
    PROGRESS = "\033[92m"  # Light green
    SUCCESS = "\033[92m"  # Light green
    FAIL = "\033[91m"  # Light red


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support"""

    COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.INFO,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.CRITICAL,
    }

    def format(self, record):
        # Add color to level name
        if record.levelno in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelno]}{record.levelname}{Colors.RESET}"
            )

        # Add color to API names if present
        if hasattr(record, "api_name"):
            record.api_name = f"{Colors.API}{record.api_name}{Colors.RESET}"

        return super().format(record)


class ProgressFormatter(logging.Formatter):
    """Formatter optimized for progress tracking"""

    def format(self, record):
        # Format progress messages specially
        if hasattr(record, "is_progress") and record.is_progress:
            # Simplified format for progress: [API] Progress message
            if hasattr(record, "api_name"):
                return f"{Colors.PROGRESS}[{record.api_name}]{Colors.RESET} {record.getMessage()}"
            return f"{Colors.PROGRESS}▶{Colors.RESET} {record.getMessage()}"

        return super().format(record)


def setup_logging(
    level: str | None = None,
    use_colors: bool | None = None,
    log_file: str | None = None,
) -> None:
    """
    Configure logging for SciLEx.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or WARNING
        use_colors: Enable colored output. Defaults to LOG_COLOR env var or auto-detect
        log_file: Optional file path to write logs to
    """
    # Determine log level
    if level is None:
        level = os.environ.get("LOG_LEVEL", "WARNING").upper()

    log_level = getattr(logging, level, logging.WARNING)

    # Determine if colors should be used
    if use_colors is None:
        use_colors_env = os.environ.get("LOG_COLOR", "").lower()
        if use_colors_env:
            use_colors = use_colors_env in ("true", "1", "yes")
        else:
            # Auto-detect: use colors if stdout is a terminal
            use_colors = sys.stdout.isatty()

    # Create formatters
    if use_colors:
        console_format = ColoredFormatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
    else:
        console_format = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        # File logs always use non-colored format
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)

    # Log the configuration
    root_logger.debug(
        f"Logging configured: level={level}, colors={use_colors}, file={log_file}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (use __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class ProgressTracker:
    """
    Helper class for tracking and logging progress with reduced verbosity.

    Usage:
        tracker = ProgressTracker("SemanticScholar", total_pages=50, log_interval=10)

        for page in range(1, 51):
            # ... collect page ...
            tracker.update(page, papers_collected=25)
    """

    def __init__(
        self,
        name: str,
        total_items: int,
        log_interval: int = 10,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize progress tracker.

        Args:
            name: Name of the operation (e.g., API name)
            total_items: Total number of items to process
            log_interval: Log progress every N items
            logger: Logger instance (uses root logger if None)
        """
        self.name = name
        self.total_items = total_items
        self.log_interval = log_interval
        self.logger = logger or logging.getLogger()
        self.current_item = 0
        self.extra_data = {}

    def update(self, current: int, **kwargs):
        """
        Update progress and log if needed.

        Args:
            current: Current item number
            **kwargs: Additional data to track (e.g., papers_collected=100)
        """
        self.current_item = current
        self.extra_data.update(kwargs)

        # Log at intervals, at completion, or at start
        should_log = (
            current == 1
            or current % self.log_interval == 0
            or current >= self.total_items
        )

        if should_log:
            progress_pct = (current / self.total_items) * 100

            # Build message with extra data
            extra_info = ""
            if self.extra_data:
                extra_parts = [f"{k}={v}" for k, v in self.extra_data.items()]
                extra_info = f" ({', '.join(extra_parts)})"

            # Special formatting for completion
            if current >= self.total_items:
                symbol = (
                    f"{Colors.SUCCESS}✓{Colors.RESET}" if sys.stdout.isatty() else "✓"
                )
                self.logger.info(
                    f"{symbol} [{self.name}] Completed: {current}/{self.total_items}{extra_info}",
                    extra={"is_progress": True, "api_name": self.name},
                )
            else:
                self.logger.info(
                    f"[{self.name}] Progress: {current}/{self.total_items} ({progress_pct:.1f}%){extra_info}",
                    extra={"is_progress": True, "api_name": self.name},
                )

    def complete(self, **kwargs):
        """Mark operation as complete with final stats"""
        self.extra_data.update(kwargs)
        self.update(self.total_items)


def log_section(logger: logging.Logger, title: str, level: str = "INFO"):
    """
    Log a section header with visual separator.

    Args:
        logger: Logger instance
        title: Section title
        level: Log level (INFO, DEBUG, etc.)
    """
    log_func = getattr(logger, level.lower())
    separator = "=" * 70
    log_func(separator)
    log_func(title)
    log_func(separator)


def log_api_start(
    logger: logging.Logger, api_name: str, rate_limit: float, total_queries: int
):
    """
    Log API collection start with configuration.

    Args:
        logger: Logger instance
        api_name: Name of the API
        rate_limit: Rate limit in requests/second
        total_queries: Total number of queries
    """
    logger.info(
        f"[{api_name}] Starting collection: {total_queries} queries (rate limit: {rate_limit} req/sec)",
        extra={"api_name": api_name},
    )


def log_api_complete(
    logger: logging.Logger, api_name: str, papers_collected: int, elapsed_seconds: float
):
    """
    Log API collection completion with stats.

    Args:
        logger: Logger instance
        api_name: Name of the API
        papers_collected: Number of papers collected
        elapsed_seconds: Time elapsed in seconds
    """
    symbol = f"{Colors.SUCCESS}✓{Colors.RESET}" if sys.stdout.isatty() else "✓"
    logger.info(
        f"{symbol} [{api_name}] Completed: {papers_collected} papers in {elapsed_seconds:.1f}s",
        extra={"api_name": api_name},
    )


def log_collection_summary(
    logger: logging.Logger, total_papers: int, total_time: float, apis_used: list
):
    """
    Log final collection summary.

    Args:
        logger: Logger instance
        total_papers: Total papers collected
        total_time: Total time in seconds
        apis_used: List of API names used
    """
    log_section(logger, "Collection Summary")
    logger.info(f"Total papers collected: {total_papers}")
    logger.info(f"Total time: {total_time:.1f}s ({total_time / 60:.1f}m)")
    logger.info(f"APIs used: {', '.join(apis_used)}")
    logger.info(f"Average speed: {total_papers / total_time:.1f} papers/sec")
