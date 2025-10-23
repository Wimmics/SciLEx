"""Configuration management endpoints."""
from fastapi import APIRouter, HTTPException

from ..schemas.config import ScilexConfig, APIConfig
from ..services.config_sync import ConfigSyncService

router = APIRouter(prefix="/api/config", tags=["config"])
config_service = ConfigSyncService()


@router.get("/scilex", response_model=ScilexConfig)
async def get_scilex_config():
    """Get current scilex.config.yml"""
    config = config_service.read_scilex_config()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration file not found")
    return config


@router.put("/scilex")
async def update_scilex_config(config: ScilexConfig):
    """Update scilex.config.yml"""
    try:
        config_service.write_scilex_config(config)
        return {"status": "success", "message": "Configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/api", response_model=APIConfig)
async def get_api_config():
    """Get current api.config.yml (with keys masked)"""
    config = config_service.read_api_config()
    if not config:
        raise HTTPException(status_code=404, detail="API configuration file not found")
    return config.mask_keys()


@router.put("/api")
async def update_api_config(config: APIConfig):
    """Update api.config.yml"""
    try:
        config_service.write_api_config(config)
        return {"status": "success", "message": "API configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save API configuration: {str(e)}")


@router.get("/exists")
async def check_configs_exist():
    """Check which config files exist."""
    return {
        "scilex": config_service.config_exists("scilex"),
        "api": config_service.config_exists("api")
    }
