"""Application configuration settings."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # App info
    app_name: str = "SciLEx GUI"
    version: str = "1.0.0"

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent.parent
    config_dir: Path = project_root / "src"
    output_dir: Path = project_root / "output"
    db_path: Path = Path.home() / ".scilex" / "gui.db"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_prefix = "SCILEX_"


settings = Settings()

# Ensure database directory exists
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
