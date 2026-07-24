r"""
Centralized logging configuration for Packing Tool.

This module provides a robust, production-ready logging system with:
- Structured JSON logging for easy parsing and analysis
- Automatic file rotation (prevents log files from growing indefinitely)
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Automatic cleanup of old logs (retention policy)
- Both file and console output for development and production

For small warehouse operations, proper logging is essential for:
- Troubleshooting issues without technical support staff
- Auditing packing operations (who did what, when)
- Monitoring application health and performance
- Debugging network/file server issues
- Compliance and quality control tracking

Log file location: \\server\...\0UFulfilment\Logs\packing_tool\
Log file format: packing_tool.log (current), packing_tool.log.YYYY-MM-DD (rotated)
Rotates at midnight; keeps LogRetentionDays worth of rotated files

Example log entry (JSON format):
    {"timestamp": "2025-11-05T14:30:45.123", "level": "INFO", "tool": "packing_tool",
     "module": "PackerLogic", "function": "process_sku_scan", "line": 465,
     "message": "SKU matched: SKU-CREAM-01"}
"""

# Standard library imports
import logging  # Core logging framework
import json  # JSON formatting for structured logging
import os  # Environment variables and paths
from datetime import datetime  # Log rotation and cleanup
from pathlib import Path  # Modern path handling
from logging.handlers import TimedRotatingFileHandler  # Automatic daily log rotation + retention
from typing import Optional, Dict, Any  # Type hints
import configparser  # Reading config.ini settings


class StructuredJSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.

    Outputs log records as JSON with fields:
    - timestamp: ISO 8601 format with milliseconds
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - tool: Always "packing_tool"
    - module: Module name
    - function: Function name
    - line: Line number
    - message: Log message
    - exc_info: Exception information (if present)
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.

        Args:
            record: LogRecord to format

        Returns:
            JSON string with structured log data
        """
        # Build structured log entry
        log_data: Dict[str, Any] = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'tool': 'packing_tool',
            'module': record.name,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exc_info'] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False)


class AppLogger:
    """
    Centralized application logger with file rotation and cleanup.

    This class implements the singleton pattern for logging configuration.
    It ensures that logging is set up only once during application startup,
    regardless of how many modules import and use the logger.

    Features:
    - Single configuration point for entire application
    - Automatic daily log rotation at midnight (one file per day)
    - Old log cleanup (prevents log directory from growing indefinitely)
    - Both file and console logging (useful for development and debugging)

    The logging system is configured from config.ini with these settings:
    - LogLevel: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - LogRetentionDays: How many rotated (past-day) log files to keep

    Attributes:
        _instance: Singleton logger instance (class-level)
        _initialized: Whether logging has been configured (class-level)
    """

    # Class-level attributes for singleton pattern
    _instance: Optional[logging.Logger] = None
    _initialized: bool = False

    @classmethod
    def get_logger(cls, name: str = 'PackingTool') -> logging.Logger:
        """
        Get or create application logger with lazy initialization.

        This is the main entry point for getting a logger instance.
        The first call initializes the logging system; subsequent calls
        return logger instances without reconfiguration.

        Usage in modules:
            from logger import get_logger
            logger = get_logger(__name__)  # __name__ = module name
            logger.info("Starting operation")

        Args:
            name: Logger name, typically the module name (__name__)
                 This allows filtering logs by module in log analysis
                 Examples: "PackerLogic", "SessionManager", "main"

        Returns:
            Configured logger instance for the specified name
            All loggers share the same handlers and configuration
        """
        # Initialize logging configuration on first call (thread-safe)
        if not cls._initialized:
            cls._setup_logging()
            cls._initialized = True

        # Return logger for the specified name
        # Python's logging system manages logger instances automatically
        return logging.getLogger(name)

    @classmethod
    def _setup_logging(cls):
        """
        Setup logging configuration from config.ini.

        This method is called automatically on first logger access.
        It configures:
        1. Log directory and file path
        2. Log level (from config or default to INFO)
        3. Log formatters (timestamp, module, level, function, line, message)
        4. File handler that rotates at midnight and prunes old files
        5. Console handler (for development and debugging)

        Log file naming convention (TimedRotatingFileHandler, when='midnight'):
            packing_tool.log             (today, currently being written)
            packing_tool.log.2025-11-03  (yesterday, rotated at midnight)
            packing_tool.log.2025-11-02  (older)
            ... automatically pruned once there are more than LogRetentionDays

        For small warehouses:
        - Daily log files make it easy to review yesterday's issues
        - Automatic pruning prevents disk space problems on PCs with limited storage
        - Console output helps during setup and troubleshooting
        - Structured format enables log analysis tools (grep, text editors)
        """
        # Load configuration from config.ini
        config = cls._load_config()

        # === LOG DIRECTORY SETUP ===
        # Store logs on centralized file server for unified logging
        # Get base path from config
        file_server_path = config.get('Network', 'FileServerPath',
                                      fallback=r'\\192.168.88.101\_Fulfilment_\0UFulfilment')

        # Centralized logs location: \\server\...\0UFulfilment\Logs\packing_tool\
        log_dir = Path(file_server_path) / "Logs" / "packing_tool"

        try:
            log_dir.mkdir(parents=True, exist_ok=True)  # Create if doesn't exist
        except Exception as e:
            # Fallback to local directory if server is not accessible
            log_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"Warning: Could not access server logs directory. Using local: {log_dir}. Error: {e}")

        # === LOG FILE PATH ===
        # Fixed base filename — TimedRotatingFileHandler appends the date to
        # rotated (past-day) files, e.g. packing_tool.log.2025-11-04
        log_file = log_dir / "packing_tool.log"

        # === LOG LEVEL CONFIGURATION ===
        # Read from config.ini, default to INFO if not specified
        # Levels: DEBUG (most verbose) -> INFO -> WARNING -> ERROR -> CRITICAL (least verbose)
        log_level_str = config.get('Logging', 'LogLevel', fallback='INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        # === RETENTION CONFIGURATION ===
        # Number of rotated (past-day) log files to keep before the oldest is deleted
        retention_days = config.getint('Logging', 'LogRetentionDays', fallback=30)

        # === LOG FORMATTERS ===
        # JSON formatter for file (structured logging for easy parsing)
        json_formatter = StructuredJSONFormatter()

        # Human-readable formatter for console
        # Format: timestamp | module | level | function:line | message
        # Example: 2025-11-05 14:30:45 | PackerLogic | INFO | process_sku_scan:465 | SKU matched
        console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'  # Readable date format
        )

        # === FILE HANDLER ===
        # TimedRotatingFileHandler rotates at midnight and keeps backupCount
        # rotated files, deleting the oldest automatically — no manual cleanup needed.
        # encoding='utf-8': Support Unicode characters (important for international clients)
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            backupCount=retention_days,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(json_formatter)  # Use JSON formatter for file logs

        # === CONSOLE HANDLER ===
        # Outputs logs to console (terminal/command prompt)
        # Useful for:
        # - Development and debugging
        # - Seeing real-time errors during operation
        # - Quick troubleshooting without opening log files
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(console_formatter)  # Use readable format for console

        # === CONFIGURE ROOT LOGGER ===
        # All module loggers inherit from root logger configuration
        # This ensures consistent logging across entire application
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)    # Log to file
        root_logger.addHandler(console_handler)  # Log to console

        # === LOG APPLICATION STARTUP ===
        # Visual separator in logs to mark application start
        # Makes it easy to identify where each application session begins
        logger = logging.getLogger('PackingTool')
        logger.info("=" * 80)
        logger.info("Packing Tool Started")
        logger.info(f"Log Level: {log_level_str}")
        logger.info(f"Log File: {log_file}")
        logger.info("=" * 80)

    @staticmethod
    def _load_config() -> configparser.ConfigParser:
        """
        Load configuration from config.ini.

        This method reads logging configuration from config.ini, which should be
        located in the application's root directory. If the file doesn't exist,
        returns an empty ConfigParser (methods will use default values).

        Configuration options:
            [Logging]
            LogLevel = INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
            LogRetentionDays = 30       # Rotated (past-day) log files to keep

        Returns:
            ConfigParser object with loaded configuration
            Returns empty ConfigParser if config.ini not found (non-fatal)
        """
        config = configparser.ConfigParser()
        config_path = Path('config.ini')

        if config_path.exists():
            # Read config file with UTF-8 encoding (supports international characters)
            config.read(config_path, encoding='utf-8')
        # If config doesn't exist, return empty ConfigParser
        # Calling code will use fallback defaults (INFO level, 30 days retention)

        return config


# Convenience functions
def get_logger(name: str = 'PackingTool') -> logging.Logger:
    """
    Get application logger.

    Args:
        name: Logger name (default: 'PackingTool')

    Returns:
        Configured logger instance

    Example:
        >>> from logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Starting process")
    """
    return AppLogger.get_logger(name)
