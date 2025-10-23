import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging

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


if __name__ == "__main__":
    txt_filters = main_config["aggregate_txt_filter"]
    get_citation = main_config["aggregate_get_citations"]
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

            # Deduplicate records
            df_clean = deduplicate(df)
            df_clean.reset_index(drop=True, inplace=True)
            logging.info(f"After deduplication: {len(df_clean)} unique papers")

            # Apply quality filters if configured
            quality_filters = main_config.get("quality_filters", {})
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

            if get_citation:
                df_clean["extra"] = ""
                df_clean["nb_cited"] = ""
                df_clean["nb_citation"] = ""

                total_papers = len(df_clean)
                papers_with_doi = df_clean["DOI"].apply(is_valid).sum()
                logging.info(f"Fetching citation data for {papers_with_doi}/{total_papers} papers with valid DOIs")
                logging.info("This may take 10-30 minutes depending on paper count (rate limit: ~5 papers/second)")

                for index, row in tqdm(df_clean.iterrows(), total=total_papers, desc="Fetching citations", unit="paper"):
                    doi = row.get("DOI")
                    logging.debug(f"Processing DOI: {doi}")
                    if is_valid(doi):
                        citations = cit_tools.getRefandCitFormatted(str(doi))
                        df_clean.loc[index, ["extra"]] = str(citations)
                        nb_ = cit_tools.countCitations(citations)
                        df_clean.loc[index, ["nb_cited"]] = nb_["nb_cited"]
                        df_clean.loc[index, ["nb_citation"]] = nb_["nb_citations"]

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
