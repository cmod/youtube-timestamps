"""Configuration loader for environment variables and YAML config."""

import os
from pathlib import Path
from typing import Dict, Any
import yaml
from dotenv import load_dotenv


class ConfigLoader:
    """Load and manage configuration from .env and config.yaml."""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the config loader.

        Args:
            config_path: Path to the YAML configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.api_key: str = ""

    def load(self) -> Dict[str, Any]:
        """Load configuration from .env and config.yaml.

        Returns:
            Dictionary containing all configuration

        Raises:
            FileNotFoundError: If config.yaml doesn't exist
            ValueError: If OPENAI_API_KEY is not set
        """
        # Load environment variables from .env
        load_dotenv()

        # Get OpenAI API key
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "OPENAI_API_KEY not found or invalid. "
                "Please set it in .env file. "
                "Get your API key from: https://platform.openai.com/api-keys"
            )

        # Get Google API key (optional)
        google_api_key = os.getenv("GOOGLE_API_KEY", "")
        if google_api_key == "your_google_api_key_here":
            google_api_key = ""

        # Load YAML configuration
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}. "
                "Please create it from the documentation."
            )

        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Add API keys to config for easy access
        self.config['openai_api_key'] = self.api_key
        self.config['google_api_key'] = google_api_key

        return self.config

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation.

        Args:
            key_path: Path to the key using dot notation (e.g., 'audio.format')
            default: Default value if key doesn't exist

        Returns:
            Configuration value or default

        Example:
            config.get('topic_analysis.model')  # Returns 'gpt-4-turbo-preview'
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Convenience function to load configuration.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary containing all configuration
    """
    loader = ConfigLoader(config_path)
    return loader.load()
