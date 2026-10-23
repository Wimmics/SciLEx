"""Export SciLEx BibTeX output to RDF/Turtle format.

Reads the aggregated BibTeX file (preferring the citations-enriched version)
and converts it to RDF using the BIBO/DCTERMS/FOAF ontologies.  Papers with a
``references`` field emit ``bibo:cites`` triples.

Usage:
    scilex-export-turtle [--format turtle|n3|xml] [--base-uri URI] [--input PATH]

Output is written to:
    {output_dir}/{collect_name}/aggregated_results.ttl
"""

import argparse
import logging
import os
import sys

from scilex.config_defaults import DEFAULT_OUTPUT_DIR
from scilex.constants import normalize_path_component
from scilex.crawlers.utils import load_all_configs
from scilex.export_to_bibtex import BIBTEX_CITATIONS_FILENAME, BIBTEX_PLAIN_FILENAME
from scilex.logging_config import setup_logging
from scilex.rdf import convert_to_string

setup_logging()
logger = logging.getLogger(__name__)

DEFAULT_BASE_URI = "http://example.org/pub/"

FORMAT_EXTENSIONS = {
    "turtle": ".ttl",
    "n3": ".n3",
    "xml": ".rdf",
}


def load_config() -> dict:
    """Load scilex.config.yml."""
    configs = load_all_configs({"main_config": "scilex.config.yml"})
    return configs["main_config"]


def main():
    """Entry point for Turtle export."""
    parser = argparse.ArgumentParser(description="Export SciLEx BibTeX to RDF/Turtle")
    parser.add_argument(
        "--format",
        choices=["turtle", "n3", "xml"],
        default="turtle",
        help="RDF serialisation format (default: turtle)",
    )
    parser.add_argument(
        "--base-uri",
        default=None,
        help=f"Base URI for locally-minted resource URIs (default: {DEFAULT_BASE_URI})",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to input .bib file (overrides auto-detection from config)",
    )
    args = parser.parse_args()

    try:
        config = load_config()

        if "collect_name" not in config:
            raise ValueError("collect_name not specified in scilex.config.yml")

        output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
        collect_name = normalize_path_component(config["collect_name"])
        collect_dir = os.path.join(output_dir, collect_name)

        # Resolve input BibTeX path
        if args.input:
            bib_path = args.input
        else:
            # Prefer citations-enriched file; fall back to plain aggregated
            enriched = os.path.join(collect_dir, BIBTEX_CITATIONS_FILENAME)
            plain = os.path.join(collect_dir, BIBTEX_PLAIN_FILENAME)
            if os.path.exists(enriched):
                bib_path = enriched
                logger.info("Using citations-enriched BibTeX file")
            elif os.path.exists(plain):
                bib_path = plain
                logger.info("Using plain aggregated BibTeX file")
            else:
                raise FileNotFoundError(
                    f"No BibTeX file found in {collect_dir}. "
                    "Run scilex-export-bibtex (and optionally scilex-enrich-citations) first."
                )

        logger.info(f"Input:  {bib_path}")

        base_uri = args.base_uri or DEFAULT_BASE_URI
        fmt = args.format
        ext = FORMAT_EXTENSIONS[fmt]
        output_file = os.path.join(collect_dir, f"aggregated_results{ext}")

        logger.info(f"Converting to {fmt.upper()}...")
        rdf_str = convert_to_string(
            bib_path, base_uri=base_uri, fmt=fmt, collect_name=collect_name
        )

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(rdf_str)

        logger.info(f"Output: {output_file}")
        print(f"\nRDF export complete: {output_file}")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during Turtle export: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
