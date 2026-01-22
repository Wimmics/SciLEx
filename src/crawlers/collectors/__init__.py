"""
Collectors package for SciLEx.

This module provides API collectors for various academic paper databases.
"""

from .arxiv import Arxiv_collector
from .base import API_collector, Filter_param
from .dblp import DBLP_collector
from .elsevier import Elsevier_collector
from .google_scholar import GoogleScholarCollector
from .hal import HAL_collector
from .ieee import IEEE_collector
from .istex import Istex_collector
from .openalex import OpenAlex_collector
from .pubmed_central import PubMedCentral_collector
from .semantic_scholar import SemanticScholar_collector
from .springer import Springer_collector

__all__ = [
    "API_collector",
    "Filter_param",
    "SemanticScholar_collector",
    "IEEE_collector",
    "Elsevier_collector",
    "DBLP_collector",
    "OpenAlex_collector",
    "HAL_collector",
    "Arxiv_collector",
    "Istex_collector",
    "Springer_collector",
    "GoogleScholarCollector",
    "PubMedCentral_collector",
]
