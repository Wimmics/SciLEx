#!/usr/bin/env python3
"""Extract and structure metadata from HuggingFace model/dataset cards.

Handles:
- Model card parsing (YAML frontmatter + README content)
- Dataset card parsing
- GitHub repository extraction (only URLs actually present in card data)
- Architecture/framework identification
- Paper reference extraction
"""

import re

GITHUB_URL_PATTERN = re.compile(r"https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+")


class MetadataExtractor:
    """Extract structured metadata from HuggingFace resource cards.

    Extracts:
    - Model architecture (BERT, GPT, T5, etc.)
    - Framework (PyTorch, TensorFlow, JAX)
    - Training datasets
    - GitHub repository URLs
    - Paper references (DOI, arXiv)
    """

    # Known model architecture patterns (from getLPWC_collect.py model_list)
    ARCHITECTURES = {
        "bert": "BERT",
        "roberta": "RoBERTa",
        "gpt": "GPT",
        "gpt2": "GPT-2",
        "gpt3": "GPT-3",
        "gpt4": "GPT-4",
        "t5": "T5",
        "bart": "BART",
        "electra": "ELECTRA",
        "albert": "ALBERT",
        "xlnet": "XLNet",
        "distilbert": "DistilBERT",
        "spanbert": "SpanBERT",
        "scibert": "SciBERT",
        "pubmedbert": "PubMedBERT",
        "biobert": "BioBERT",
        "transformerxl": "TransformerXL",
        "mt5": "mT5",
        "deberta": "DeBerta",
        "glm": "GLM",
        "comet": "COMET",
        "mbart": "mBART",
        "rebel": "REBEL",
        "pegasus": "PEGASUS",
        "bertsum": "BERTSum",
        "pure": "PURE",
        "casrel": "CasRel",
        "flan": "Flan",
        "llama": "LLAMA",
        "vicuna": "VICUNA",
        "alpaca": "Alpaca",
        "luke": "LUKE",
        "clip": "CLIP",
        "xlm": "XLM",
        "kbert": "KBERT",
        "kepler": "KEPLER",
        "flair": "Flair",
        "longformer": "LongFormer",
    }

    # Prefix fallback limits (avoid "purely" -> PURE, "clipboard" -> CLIP)
    MIN_PREFIX_KEY_LENGTH = 5
    MAX_PREFIX_REMAINDER = 4

    # Framework mappings
    FRAMEWORKS = {
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "jax": "JAX",
        "flax": "Flax",
        "keras": "Keras",
    }

    def extract_model_metadata(self, model_dict: dict) -> dict:
        """Extract structured metadata from HF model dictionary.

        Args:
            model_dict: Model info from HFClient.search_models_by_title()

        Returns:
            Dictionary with extracted metadata:
            {
                "architecture": "BERT" | "GPT" | "T5" | None,
                "framework": "PyTorch" | "TensorFlow" | None,
                "datasets": ["squad", "glue"],
                "github_url": "https://github.com/..." | None,
                "pipeline_tag": "text-classification",
            }
        """
        result = {
            "architecture": None,
            "framework": None,
            "datasets": [],
            "github_url": None,
            "pipeline_tag": model_dict.get("pipeline_tag"),
        }

        # Extract architecture from tags or model name
        tags = model_dict.get("tags", [])
        model_id = model_dict.get("modelId", "").lower()

        result["architecture"] = self._identify_architecture(model_id, tags)

        # Extract framework
        result["framework"] = self._identify_framework(tags)

        # Extract datasets from card_data
        card_data = model_dict.get("card_data", {})
        if isinstance(card_data, dict) and "datasets" in card_data:
            datasets = card_data.get("datasets", [])
            if isinstance(datasets, list):
                result["datasets"] = datasets

        # Only report GitHub URLs actually present in the card data
        result["github_url"] = self._find_github_url(card_data)

        return result

    def extract_paper_resources(self, paper_dict: dict, linked_resources: dict) -> dict:
        """Extract metadata from HF paper and its linked resources.

        Args:
            paper_dict: Paper info from HFClient.search_papers_by_title()
            linked_resources: Result from HFClient.get_paper_linked_resources()
                Contains: {"citing_models": [...], "citing_datasets": [...]}

        Returns:
            Dictionary with extracted metadata:
            {
                "architecture": "BERT" | "GPT" | None,
                "framework": "PyTorch" | "TensorFlow" | None,
                "datasets": ["squad", "glue"],
                "pipeline_tag": "text-classification",
                "paper_id": "2409.17957"
            }
        """
        result = {
            "architecture": None,
            "framework": None,
            "datasets": [],
            "pipeline_tag": None,
            "paper_id": paper_dict.get("id"),
        }

        # Extract from citing models (use most popular model as primary)
        models = linked_resources.get("citing_models", [])
        if models:
            # Sort by downloads to get most popular
            models_sorted = sorted(
                models, key=lambda m: m.get("downloads", 0), reverse=True
            )
            primary_model = models_sorted[0]

            # Extract architecture from primary model
            tags = primary_model.get("tags", [])
            model_id = primary_model.get("modelId", "").lower()
            result["architecture"] = self._identify_architecture(model_id, tags)

            # Extract framework
            result["framework"] = self._identify_framework(tags)

            # Extract pipeline_tag
            result["pipeline_tag"] = primary_model.get("pipeline_tag")

            # Extract datasets from card_data
            card_data = primary_model.get("card_data", {})
            if isinstance(card_data, dict) and "datasets" in card_data:
                datasets = card_data.get("datasets", [])
                if isinstance(datasets, list):
                    result["datasets"].extend(datasets)

        # Extract from citing datasets
        datasets = linked_resources.get("citing_datasets", [])
        for dataset in datasets:
            dataset_id = dataset.get("datasetId")
            if dataset_id and dataset_id not in result["datasets"]:
                result["datasets"].append(dataset_id)

        return result

    def _identify_architecture(self, model_id: str, tags: list[str]) -> str | None:
        """Identify model architecture from model ID or tags.

        Args:
            model_id: Model ID (lowercase)
            tags: List of tags

        Returns:
            Architecture name or None
        """
        for tokens in (self._tokenize(model_id), self._tokenize(" ".join(tags or []))):
            # Whole-token match; dict order breaks ties (e.g. "flan-t5" -> T5)
            matched = [
                index for index, key in enumerate(self.ARCHITECTURES) if key in tokens
            ]
            if matched:
                return list(self.ARCHITECTURES.values())[min(matched)]

            # Compound fallback ("bertweet" -> BERT): longest key first
            for key in sorted(self.ARCHITECTURES, key=len, reverse=True):
                if len(key) < self.MIN_PREFIX_KEY_LENGTH:
                    continue
                for token in tokens:
                    if (
                        token.startswith(key)
                        and len(token) - len(key) <= self.MAX_PREFIX_REMAINDER
                    ):
                        return self.ARCHITECTURES[key]

        return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text on [-_/. ] and whitespace into lowercase tokens."""
        return [token for token in re.split(r"[-_/.\s]+", text.lower()) if token]

    @staticmethod
    def _find_github_url(card_data) -> str | None:
        """Return the first GitHub URL found in card data values, else None."""
        if not isinstance(card_data, dict):
            return None
        for value in card_data.values():
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                if isinstance(candidate, str):
                    match = GITHUB_URL_PATTERN.search(candidate)
                    if match:
                        return match.group(0).rstrip(".,;)")
        return None

    def _identify_framework(self, tags: list[str]) -> str | None:
        """Identify ML framework from tags.

        Args:
            tags: List of tags

        Returns:
            Framework name or None
        """
        if not tags:
            return None

        tags_lower = " ".join(tags).lower()

        for key, name in self.FRAMEWORKS.items():
            if key in tags_lower:
                return name

        return None
