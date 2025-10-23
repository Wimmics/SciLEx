"""Service for bidirectional YAML config synchronization."""
import yaml
from pathlib import Path
from typing import Optional

from ..config import settings
from ..schemas.config import ScilexConfig, APIConfig


class ConfigSyncService:
    """Manages reading/writing YAML configuration files."""

    def __init__(self):
        self.scilex_config_path = settings.config_dir / "scilex.config.yml"
        self.api_config_path = settings.config_dir / "api.config.yml"

    def read_scilex_config(self) -> Optional[ScilexConfig]:
        """Read scilex.config.yml and return validated schema."""
        if not self.scilex_config_path.exists():
            return None

        with open(self.scilex_config_path, 'r') as f:
            data = yaml.safe_load(f)

        return ScilexConfig(**data)

    def write_scilex_config(self, config: ScilexConfig) -> None:
        """Write ScilexConfig to scilex.config.yml atomically."""
        # Convert to dict
        data = config.model_dump(exclude_none=True)

        # Write to temp file first (atomic)
        temp_path = self.scilex_config_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        # Rename (atomic on POSIX)
        temp_path.rename(self.scilex_config_path)

    def read_api_config(self) -> Optional[APIConfig]:
        """Read api.config.yml and return validated schema."""
        if not self.api_config_path.exists():
            return None

        with open(self.api_config_path, 'r') as f:
            data = yaml.safe_load(f)

        return APIConfig(**data)

    def write_api_config(self, config: APIConfig) -> None:
        """Write APIConfig to api.config.yml atomically."""
        # Convert to dict
        data = config.model_dump(exclude_none=True)

        # Write to temp file first (atomic)
        temp_path = self.api_config_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        # Rename (atomic on POSIX)
        temp_path.rename(self.api_config_path)

    def config_exists(self, config_type: str) -> bool:
        """Check if config file exists."""
        if config_type == "scilex":
            return self.scilex_config_path.exists()
        elif config_type == "api":
            return self.api_config_path.exists()
        return False
