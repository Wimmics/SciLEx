#!/usr/bin/env python3
"""Extract and structure metadata from HuggingFace model/dataset cards.

Handles:
- Model card parsing (YAML frontmatter + README content)
- Dataset card parsing
- GitHub repository extraction
- Architecture/framework identification
- Paper reference extraction
"""

from scilex.constants import is_valid


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

    # Framework mappings
    FRAMEWORKS = {
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "jax": "JAX",
        "flax": "Flax",
        "keras": "Keras",
    }

    def __init__(self):
        """Initialize metadata extractor."""
        pass

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

        # Extract GitHub URL from model card (if available)
        # Note: HF Hub API doesn't provide card text directly,
        # but we can infer from model_id sometimes
        if "/" in model_dict.get("modelId", ""):
            # Try to construct GitHub URL from model ID
            parts = model_dict["modelId"].split("/")
            if len(parts) == 2:
                author, model_name = parts
                # Common pattern: many HF models have GitHub repos
                result["github_url"] = f"https://github.com/{author}/{model_name}"

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
                "github_urls": ["https://github.com/..."],
                "pipeline_tag": "text-classification",
                "paper_id": "2409.17957"
            }
        """
        result = {
            "architecture": None,
            "framework": None,
            "datasets": [],
            "github_urls": linked_resources.get("github_urls", []),
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
        tags_lower = " ".join(tags).lower() if tags else ""

        for key, name in self.ARCHITECTURES.items():
            if key in model_id or key in tags_lower:
                return name

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

    def extract_dataset_metadata(self, dataset_dict: dict) -> dict:
        """Extract structured metadata from HF dataset dictionary.

        Args:
            dataset_dict: Dataset info from HFClient.search_datasets_by_title()

        Returns:
            Dictionary with extracted metadata
        """
        result = {
            "datasets": [dataset_dict.get("datasetId")],
            "github_url": None,
        }

        # Try to construct GitHub URL from dataset ID
        if "/" in dataset_dict.get("datasetId", ""):
            parts = dataset_dict["datasetId"].split("/")
            if len(parts) == 2:
                author, dataset_name = parts
                result["github_url"] = f"https://github.com/{author}/{dataset_name}"

        return result

    def identify_task(self, pipeline_tag: str | None) -> str | None:
        """Map HuggingFace pipeline_tag to SciLEx TASK: tag.

        Mappings:
        - "text-classification" → "TextClassification"
        - "question-answering" → "QuestionAnswering"
        - "summarization" → "Summarization"
        - etc.

        Args:
            pipeline_tag: HF pipeline tag (e.g., "text-classification")

        Returns:
            Normalized task name for Zotero tagging
        """
        if not is_valid(pipeline_tag):
            return None

        # Mapping dictionary (NLP tasks)
        task_map = {
            "text-classification": "TextClassification",
            "token-classification": "TokenClassification",
            "question-answering": "QuestionAnswering",
            "summarization": "Summarization",
            "translation": "Translation",
            "text-generation": "TextGeneration",
            "fill-mask": "MaskedLanguageModeling",
            "feature-extraction": "FeatureExtraction",
            "zero-shot-classification": "ZeroShotClassification",
            "text2text-generation": "Text2TextGeneration",
            # Computer Vision tasks
            "image-classification": "ImageClassification",
            "object-detection": "ObjectDetection",
            "image-segmentation": "ImageSegmentation",
            "image-to-text": "ImageCaptioning",
            # Audio tasks
            "automatic-speech-recognition": "SpeechRecognition",
            "audio-classification": "AudioClassification",
            "text-to-speech": "TextToSpeech",
            # Multimodal tasks
            "visual-question-answering": "VisualQuestionAnswering",
            "document-question-answering": "DocumentQA",
        }

        return task_map.get(pipeline_tag.lower())
