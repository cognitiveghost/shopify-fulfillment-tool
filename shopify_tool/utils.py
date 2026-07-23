import os
import logging

logger = logging.getLogger("ShopifyToolLogger")


def get_persistent_data_path(filename):
    """Gets the full path to a file in a persistent application data directory.

    This function provides a reliable way to store application data (like
    history or configuration files) in a user-specific, persistent location.
    It creates the application-specific directory if it does not already exist.

    - On Windows, it uses the `%APPDATA%` environment variable.
    - On other platforms (Linux, macOS), it uses the user's home directory (`~`).

    If the directory cannot be created (e.g., due to permissions), it logs an
    error and defaults to using the current working directory as a fallback.

    Args:
        filename (str): The name of the file to be stored (e.g.,
            "history.csv").

    Returns:
        str: The absolute path to the file within the application's data
             directory.
    """
    # Use APPDATA for Windows, or user's home directory for other platforms
    app_data_path = os.getenv("APPDATA") or os.path.expanduser("~")
    app_dir = os.path.join(app_data_path, "ShopifyFulfillmentTool")

    try:
        os.makedirs(app_dir, exist_ok=True)
    except OSError as e:
        # Fallback to current directory if AppData is not writable
        logger.error(f"Could not create AppData directory: {e}. Falling back to local directory.")
        app_dir = "."

    return os.path.join(app_dir, filename)
