"""Configuration schemas matching YAML structure."""
from typing import Optional
from pydantic import BaseModel, Field


class ScilexConfig(BaseModel):
    """Schema for scilex.config.yml"""

    # Search parameters
    keywords: list[list[str]] = Field(
        description="Dual keyword groups for search",
        example=[["machine learning", "deep learning"], ["nlp", "natural language"]]
    )
    years: list[int] = Field(
        description="Years to search",
        example=[2020, 2021, 2022, 2023, 2024]
    )
    apis: list[str] = Field(
        description="APIs to use for collection",
        example=["SemanticScholar", "OpenAlex", "IEEE"]
    )
    fields: list[str] = Field(
        default=["title", "abstract"],
        description="Fields to search in"
    )

    # Collection control
    collect: bool = Field(default=True, description="Enable collection phase")
    collect_name: str = Field(default="collection", description="Collection name")
    output_dir: str = Field(default="output", description="Output directory")
    email: Optional[str] = Field(default=None, description="Email for some APIs")

    # Aggregation options
    aggregate_txt_filter: bool = Field(default=True, description="Apply text filters")
    aggregate_get_citations: bool = Field(default=False, description="Fetch citations")
    aggregate_file: str = Field(default="aggregated_data.csv", description="Output filename")

    class Config:
        json_schema_extra = {
            "example": {
                "keywords": [["machine learning"], ["nlp"]],
                "years": [2023, 2024],
                "apis": ["SemanticScholar", "OpenAlex"],
                "fields": ["title", "abstract"],
                "collect": True,
                "collect_name": "ml_nlp_papers",
                "output_dir": "output",
                "aggregate_txt_filter": True,
                "aggregate_get_citations": False,
                "aggregate_file": "aggregated_data.csv"
            }
        }


class APIRateLimits(BaseModel):
    """Rate limits per API (requests per second)."""
    SemanticScholar: float = 1.0
    OpenAlex: float = 10.0
    Arxiv: float = 3.0
    IEEE: float = 10.0
    Elsevier: float = 6.0
    Springer: float = 1.5
    HAL: float = 10.0
    DBLP: float = 10.0
    GoogleScholar: float = 2.0
    Crossref: float = 3.0


class APIConfig(BaseModel):
    """Schema for api.config.yml (API keys masked for security)."""

    # Zotero
    zotero_api_key: Optional[str] = Field(default=None, description="Zotero API key")
    zotero_user_id: Optional[str] = Field(default=None, description="Zotero user ID")
    zotero_collection_id: Optional[str] = Field(default=None, description="Zotero collection ID")

    # API keys
    ieee_api_key: Optional[str] = Field(default=None, description="IEEE API key")
    elsevier_api_key: Optional[str] = Field(default=None, description="Elsevier API key")
    elsevier_inst_token: Optional[str] = Field(default=None, description="Elsevier institutional token")
    springer_api_key: Optional[str] = Field(default=None, description="Springer API key")
    semantic_scholar_api_key: Optional[str] = Field(default=None, description="Semantic Scholar API key")

    # Rate limits
    rate_limits: APIRateLimits = Field(default_factory=APIRateLimits)

    def mask_keys(self) -> "APIConfig":
        """Return copy with API keys masked."""
        masked = self.model_copy()
        for field in ["zotero_api_key", "ieee_api_key", "elsevier_api_key",
                      "elsevier_inst_token", "springer_api_key", "semantic_scholar_api_key"]:
            value = getattr(masked, field)
            if value:
                setattr(masked, field, "***" + value[-4:])
        return masked
