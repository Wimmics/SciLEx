import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging

import pandas as pd

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
    state_path = os.path.join(dir_collect, "state_details.json")
    logging.info(f"Starting aggregation from {state_path}")
    all_data = []
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
            df_clean = deduplicate(df)
            df_clean.reset_index(
                drop=True, inplace=True
            )  # Reset index after deduplication
            if get_citation:
                df_clean["extra"] = ""
                df_clean["nb_cited"] = ""
                df_clean["nb_citation"] = ""
                for index, row in df_clean.iterrows():
                    doi = row.get("DOI")
                    logging.debug(f"Processing DOI: {doi}")
                    if is_valid(doi):
                        citations = cit_tools.getRefandCitFormatted(str(doi))
                        df_clean.loc[index, ["extra"]] = str(citations)
                        nb_ = cit_tools.countCitations(citations)
                        df_clean.loc[index, ["nb_cited"]] = nb_["nb_cited"]
                        df_clean.loc[index, ["nb_citation"]] = nb_["nb_citations"]

            # Save to CSV
            df_clean.to_csv(
                os.path.join(dir_collect, "FileAggreg.csv"),
                sep=";",
                quotechar='"',
                quoting=csv.QUOTE_NONNUMERIC,
            )
