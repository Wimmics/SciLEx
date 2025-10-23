import argparse
import csv
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from tqdm import tqdm

import src.citations.citations_tools as cit_tools
from src.constants import MISSING_VALUE, is_valid
from src.crawlers.aggregate import (
    deduplicate,
    SemanticScholartoZoteroFormat,
    IstextoZoteroFormat,
    ArxivtoZoteroFormat,
    DBLPtoZoteroFormat,
    HALtoZoteroFormat,
    OpenAlextoZoteroFormat,
    IEEEtoZoteroFormat,
    SpringertoZoteroFormat,
    ElseviertoZoteroFormat,
    GoogleScholartoZoteroFormat,
)
from src.crawlers.utils import load_all_configs
from src.quality_validation import (
    apply_quality_filters,
    generate_data_completeness_report,
)
from src.keyword_validation import (
    generate_keyword_validation_report,
    filter_by_keywords,
)
from src.abstract_validation import (
    validate_dataframe_abstracts,
    filter_by_abstract_quality,
)
from src.duplicate_tracking import analyze_and_report_duplicates

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,  # Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log message format
    datefmt="%Y-%m-%d %H:%M:%S",  # Date format
)

config_files = {"main_config": "scilex.config.yml", "api_config": "api.config.yml"}
# Load configurations
configs = load_all_configs(config_files)
# Access individual configurations
main_config = configs["main_config"]
api_config = configs["api_config"]

# Format converters dispatcher - replaces eval() for security
FORMAT_CONVERTERS = {
    "SemanticScholar": SemanticScholartoZoteroFormat,
    "Istex": IstextoZoteroFormat,
    "Arxiv": ArxivtoZoteroFormat,
    "DBLP": DBLPtoZoteroFormat,
    "HAL": HALtoZoteroFormat,
    "OpenAlex": OpenAlextoZoteroFormat,
    "IEEE": IEEEtoZoteroFormat,
    "Springer": SpringertoZoteroFormat,
    "Elsevier": ElseviertoZoteroFormat,
    "GoogleScholar": GoogleScholartoZoteroFormat,
}

def _keyword_matches_in_abstract(keyword, abstract_text):
    """Check if keyword appears in abstract text (handles both dict and string formats)."""
    if isinstance(abstract_text, dict) and "p" in abstract_text:
        abstract_content = " ".join(abstract_text["p"]).lower()
    else:
        abstract_content = str(abstract_text).lower()
    
    return keyword in abstract_content


def _record_passes_text_filter(record, keywords):
    """Check if record contains any of the keywords in title or abstract."""
    if not keywords:
        return True

    abstract = record.get("abstract", MISSING_VALUE)
    title = record.get("title", "").lower()

    for keyword in keywords:
        # Check in title
        if keyword in title:
            return True

        # Check in abstract (if valid)
        if is_valid(abstract) and _keyword_matches_in_abstract(keyword, abstract):
            return True

    return False


# Global lock for thread-safe rate limiting
_rate_limit_lock = threading.Lock()


def _load_checkpoint(checkpoint_path):
    """Load checkpoint data if exists."""
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"Could not load checkpoint: {e}")
    return None


def _save_checkpoint(checkpoint_path, data):
    """Save checkpoint data."""
    try:
        with open(checkpoint_path, "w") as f:
            json.dump(data, f)
        logging.debug(f"Checkpoint saved to {checkpoint_path}")
    except IOError as e:
        logging.warning(f"Could not save checkpoint: {e}")


def _fetch_citation_for_paper(index, doi, stats, checkpoint_interval, checkpoint_path,
                               extras, nb_citeds, nb_citations):
    """
    Fetch citations for a single paper (thread-safe).

    Args:
        index: Paper index in DataFrame
        doi: DOI string or None
        stats: Shared dictionary for statistics tracking
        checkpoint_interval: Save checkpoint every N papers
        checkpoint_path: Path to checkpoint file
        extras: List to store citation data
        nb_citeds: List to store cited count
        nb_citations: List to store citing count

    Returns:
        dict: Result with index and status
    """
    if not is_valid(doi):
        stats["no_doi"] += 1
        return {"index": index, "status": "no_doi"}

    try:
        # Call API (with retry logic built in)
        citations, api_stats = cit_tools.getRefandCitFormatted(str(doi))

        # Track statistics
        if api_stats["cit_status"] == "success" and api_stats["ref_status"] == "success":
            stats["success"] += 1
        elif "timeout" in [api_stats["cit_status"], api_stats["ref_status"]]:
            stats["timeout"] += 1
        else:
            stats["error"] += 1

        # Store results
        extras[index] = str(citations)
        nb_ = cit_tools.countCitations(citations)
        nb_citeds[index] = nb_["nb_cited"]
        nb_citations[index] = nb_["nb_citations"]

        # Checkpoint save (thread-safe)
        if checkpoint_interval and (index + 1) % checkpoint_interval == 0:
            with _rate_limit_lock:
                checkpoint_data = {
                    "last_index": index,
                    "stats": dict(stats),
                    "extras": extras[:index+1],
                    "nb_citeds": nb_citeds[:index+1],
                    "nb_citations": nb_citations[:index+1]
                }
                _save_checkpoint(checkpoint_path, checkpoint_data)
                logging.info(f"Checkpoint saved at paper {index+1}")

        return {"index": index, "status": "success"}

    except Exception as e:
        logging.error(f"Unexpected error fetching citations for DOI {doi}: {e}")
        stats["error"] += 1
        return {"index": index, "status": "error"}


def _fetch_citations_parallel(df_clean, num_workers=3, checkpoint_interval=100,
                               checkpoint_path=None, resume_from=None):
    """
    Fetch citations in parallel using ThreadPoolExecutor.

    Args:
        df_clean: DataFrame with papers
        num_workers: Number of parallel workers
        checkpoint_interval: Save checkpoint every N papers
        checkpoint_path: Path to checkpoint file
        resume_from: Index to resume from (if resuming)

    Returns:
        tuple: (extras list, nb_citeds list, nb_citations list, stats dict)
    """
    total_papers = len(df_clean)

    # Initialize result lists
    extras = [""] * total_papers
    nb_citeds = [""] * total_papers
    nb_citations = [""] * total_papers

    # Initialize statistics (thread-safe using dict)
    stats = {
        "success": 0,
        "timeout": 0,
        "error": 0,
        "no_doi": 0
    }

    # Load from checkpoint if resuming
    start_index = 0
    if resume_from is not None:
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            start_index = checkpoint["last_index"] + 1
            stats = checkpoint["stats"]
            # Restore already processed data
            for i in range(start_index):
                extras[i] = checkpoint["extras"][i]
                nb_citeds[i] = checkpoint["nb_citeds"][i]
                nb_citations[i] = checkpoint["nb_citations"][i]
            logging.info(f"Resuming from paper {start_index}")

    papers_with_doi = df_clean["DOI"].apply(is_valid).sum()
    logging.info(f"Fetching citation data for {papers_with_doi}/{total_papers} papers with valid DOIs")
    logging.info(f"Using {num_workers} parallel workers (rate limit: ~{num_workers*2.5:.1f} papers/second)")

    # Create progress bar
    with tqdm(total=total_papers, initial=start_index, desc="Fetching citations", unit="paper") as pbar:
        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            future_to_index = {}
            for index, row in df_clean.iloc[start_index:].iterrows():
                doi = row.get("DOI")
                future = executor.submit(
                    _fetch_citation_for_paper,
                    index, doi, stats, checkpoint_interval, checkpoint_path,
                    extras, nb_citeds, nb_citations
                )
                future_to_index[future] = index

            # Process completed tasks
            for future in as_completed(future_to_index):
                result = future.result()
                pbar.update(1)

                # Update progress bar with statistics
                pbar.set_postfix({
                    "✓": stats["success"],
                    "✗": stats["error"],
                    "⏱": stats["timeout"],
                    "⊘": stats["no_doi"]
                })

    logging.info(f"Citation fetching complete: {stats['success']} successful, "
                 f"{stats['error']} errors, {stats['timeout']} timeouts, "
                 f"{stats['no_doi']} without DOI")

    return extras, nb_citeds, nb_citations, stats


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Aggregate collected papers and fetch citations")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint if available")
    parser.add_argument("--skip-citations", action="store_true",
                        help="Skip citation fetching entirely")
    parser.add_argument("--workers", type=int, default=3,
                        help="Number of parallel workers for citation fetching (default: 3)")
    parser.add_argument("--checkpoint-interval", type=int, default=100,
                        help="Save checkpoint every N papers (default: 100)")
    args = parser.parse_args()

    txt_filters = main_config["aggregate_txt_filter"]
    get_citation = main_config["aggregate_get_citations"] and not args.skip_citations
    dir_collect = os.path.join(main_config["output_dir"], main_config["collect_name"])
    # Get output filename from config, with fallback and handle leading slashes
    output_filename = main_config.get("aggregate_file", "FileAggreg.csv").lstrip("/")
    state_path = os.path.join(dir_collect, "state_details.json")
    logging.info(f"Starting aggregation from {state_path}")
    all_data = []

    # Check if state file exists
    if not os.path.isfile(state_path):
        logging.error(f"State file not found: {state_path}")
        logging.error(f"Collection directory '{dir_collect}' does not contain state_details.json")
        logging.error("Please run collection first (python src/run_collecte.py) or check 'collect_name' in scilex.config.yml")
        sys.exit(1)

    if os.path.isfile(state_path):
        logging.debug("State details file found, proceeding with aggregation")
        with open(state_path, encoding="utf-8") as read_file:
            state_details = json.load(read_file)

            # if(state_details["global"]==1):
            for api_ in state_details["details"]:
                api_data = state_details["details"][api_]
                for index in api_data["by_query"]:
                    KW = api_data["by_query"][index]["keyword"]
                    current_collect_dir = os.path.join(dir_collect, api_, index)
                    if not os.path.exists(current_collect_dir):
                        continue
                    for path in os.listdir(current_collect_dir):
                        # Check if current path is a file
                        if os.path.isfile(os.path.join(current_collect_dir, path)):
                            with open(
                                os.path.join(current_collect_dir, path)
                            ) as json_file:
                                current_page_data = json.load(json_file)
                                logging.debug(f"Loaded data from {json_file.name}")
                                for row in current_page_data["results"]:
                                    if api_ in FORMAT_CONVERTERS:
                                        # Use dispatcher dictionary instead of eval for security
                                        res = FORMAT_CONVERTERS[api_](row)
                                        if txt_filters:
                                            # Use helper function for cleaner text filtering logic
                                            if _record_passes_text_filter(res, KW):
                                                all_data.append(res)
                                        else:
                                            all_data.append(res)
                    # Create DataFrame and save aggregated results
            df = pd.DataFrame(all_data)
            logging.info(f"Aggregated {len(df)} papers from all APIs")

            # Get quality filters configuration
            quality_filters = main_config.get("quality_filters", {})

            # Deduplicate records (with fuzzy matching if configured)
            use_fuzzy = quality_filters.get("use_fuzzy_matching", True) if quality_filters else True
            fuzzy_threshold = quality_filters.get("fuzzy_threshold", 0.90) if quality_filters else 0.90
            df_clean = deduplicate(df, use_fuzzy_matching=use_fuzzy, fuzzy_threshold=fuzzy_threshold)
            df_clean.reset_index(drop=True, inplace=True)
            logging.info(f"After deduplication: {len(df_clean)} unique papers")

            # Apply quality filters if configured
            if quality_filters:
                logging.info("Applying quality filters...")
                generate_report = quality_filters.get("generate_quality_report", True)
                df_clean, quality_report = apply_quality_filters(
                    df_clean, quality_filters, generate_report
                )
                logging.info(f"After quality filtering: {len(df_clean)} papers remaining")

            # Generate data completeness report
            if quality_filters.get("generate_quality_report", True):
                completeness_report = generate_data_completeness_report(df_clean)
                logging.info(completeness_report)

            # Generate keyword validation report
            keywords = main_config.get("keywords", [])
            if keywords and quality_filters.get("generate_quality_report", True):
                keyword_report = generate_keyword_validation_report(df_clean, keywords)
                logging.info(keyword_report)

            # Abstract quality validation (Phase 2)
            if quality_filters.get("validate_abstracts", False):
                logging.info("Validating abstract quality...")
                min_quality_score = quality_filters.get("min_abstract_quality_score", 50)
                df_clean, abstract_stats = validate_dataframe_abstracts(
                    df_clean,
                    min_quality_score=min_quality_score,
                    generate_report=quality_filters.get("generate_quality_report", True)
                )

                # Optionally filter by abstract quality
                if quality_filters.get("filter_by_abstract_quality", False):
                    df_clean = filter_by_abstract_quality(
                        df_clean,
                        min_quality_score=min_quality_score
                    )
                    logging.info(f"After abstract quality filtering: {len(df_clean)} papers remaining")

            # Duplicate source tracking (Phase 2)
            if quality_filters.get("track_duplicate_sources", True):
                logging.info("Analyzing duplicate sources and API overlap...")
                analyzer, metadata_quality = analyze_and_report_duplicates(
                    df_clean,
                    generate_report=quality_filters.get("generate_quality_report", True)
                )

            if get_citation:
                # Set up checkpoint path
                checkpoint_path = os.path.join(dir_collect, "citation_checkpoint.json")

                # Fetch citations in parallel with checkpointing
                extras, nb_citeds, nb_citations, stats = _fetch_citations_parallel(
                    df_clean,
                    num_workers=args.workers,
                    checkpoint_interval=args.checkpoint_interval,
                    checkpoint_path=checkpoint_path,
                    resume_from=args.resume
                )

                # Assign results to DataFrame (efficient bulk assignment)
                df_clean["extra"] = extras
                df_clean["nb_cited"] = nb_citeds
                df_clean["nb_citation"] = nb_citations

                # Warn if high failure rate
                total_with_doi = stats["success"] + stats["error"] + stats["timeout"]
                if total_with_doi > 0:
                    failure_rate = (stats["error"] + stats["timeout"]) / total_with_doi * 100
                    if failure_rate > 10:
                        logging.warning(f"High failure rate: {failure_rate:.1f}% of API calls failed")

                # Clean up checkpoint file on success
                if os.path.exists(checkpoint_path):
                    try:
                        os.remove(checkpoint_path)
                        logging.info("Checkpoint file removed after successful completion")
                    except OSError:
                        pass

            # Save to CSV
            output_path = os.path.join(dir_collect, output_filename)
            logging.info(f"Saving {len(df_clean)} aggregated papers to {output_path}")
            df_clean.to_csv(
                output_path,
                sep=";",
                quotechar='"',
                quoting=csv.QUOTE_NONNUMERIC,
            )
            logging.info(f"Aggregation complete! Results saved to {output_path}")
