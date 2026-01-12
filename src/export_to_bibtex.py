"""
BibTeX Export for SciLEx - Alternative to Zotero push.

Exports aggregated paper data to BibTeX format for pipeline integration.
Supports DOI-based citation keys and direct PDF download links.
"""

import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_defaults import DEFAULT_AGGREGATED_FILENAME, DEFAULT_OUTPUT_DIR
from src.constants import is_valid
from src.crawlers.utils import load_all_configs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def safe_get(row, field):
    """Safely get a field from a pandas Series or dict-like object."""
    try:
        if hasattr(row, field):
            return getattr(row, field)
        return row.get(field) if hasattr(row, "get") else None
    except (AttributeError, KeyError, TypeError):
        return None


# ItemType to BibTeX entry type mapping
ITEMTYPE_TO_BIBTEX = {
    "journalArticle": "article",
    "conferencePaper": "inproceedings",
    "bookSection": "incollection",
    "book": "book",
    "preprint": "misc",
    "Manuscript": "unpublished",
}

# Special characters that need escaping in BibTeX
BIBTEX_SPECIAL_CHARS = {
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def load_config() -> dict:
    """Load scilex.config.yml configuration."""
    config_files = {
        "main_config": "scilex.config.yml",
    }
    configs = load_all_configs(config_files)
    return configs["main_config"]


def load_aggregated_data(config: dict) -> pd.DataFrame:
    """
    Load aggregated paper data from CSV file.

    Args:
        config: Configuration dictionary with output_dir and collect_name

    Returns:
        DataFrame containing aggregated paper data
    """
    output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    aggregate_file = config.get("aggregate_file", DEFAULT_AGGREGATED_FILENAME)
    dir_collect = os.path.join(output_dir, config["collect_name"])
    file_path = dir_collect + aggregate_file

    logger.info(f"Loading data from: {file_path}")

    # Try different delimiters
    for delimiter in [";", "\t", ","]:
        try:
            data = pd.read_csv(file_path, delimiter=delimiter)
            if "itemType" in data.columns and "title" in data.columns:
                logger.info(f"Loaded {len(data)} papers (delimiter: '{delimiter}')")
                return data
        except Exception as e:
            logger.debug(f"Failed to load with delimiter '{delimiter}': {e}")
            continue

    raise ValueError(
        f"Could not load CSV file with any delimiter (tried: ';', '\\t', ','). "
        f"File: {file_path}"
    )


def parse_tags(tags_str: str) -> list[str]:
    """Parse semicolon-separated tags from CSV.

    Args:
        tags_str: Semicolon-separated tags (e.g., "TASK:NER;PTM:BERT")

    Returns:
        List of tag strings
    """
    if not is_valid(tags_str):
        return []

    tags = [tag.strip() for tag in str(tags_str).split(";")]
    return [t for t in tags if t]  # Remove empty strings


def escape_bibtex(text: str) -> str:
    """
    Escape special BibTeX characters in text.

    Args:
        text: Text to escape

    Returns:
        Escaped text safe for BibTeX
    """
    if not is_valid(text):
        return ""

    text = str(text)
    for char, escaped in BIBTEX_SPECIAL_CHARS.items():
        text = text.replace(char, escaped)

    return text


def format_authors(authors_str: str) -> str:
    """
    Format semicolon-separated author list for BibTeX.

    Converts "John Smith;Jane Doe" to "John Smith and Jane Doe"

    Args:
        authors_str: Semicolon-separated author names

    Returns:
        BibTeX-formatted author list
    """
    if not is_valid(authors_str):
        return ""

    authors = [author.strip() for author in authors_str.split(";")]
    authors = [a for a in authors if a]  # Remove empty strings

    if not authors:
        return ""

    return " and ".join(authors)


def format_pages(pages_str: str) -> str:
    """
    Format page range for BibTeX (use en-dash).

    Converts "123-456" to "123--456"

    Args:
        pages_str: Page range string

    Returns:
        BibTeX-formatted page range
    """
    if not is_valid(pages_str):
        return ""

    pages_str = str(pages_str).strip()
    # Replace single dash with double dash (BibTeX en-dash)
    pages_str = pages_str.replace("-", "--")
    # But avoid double-replacing if already double
    pages_str = pages_str.replace("----", "--")

    return pages_str


def extract_year(date_str: str) -> str:
    """
    Extract year from date string.

    Handles ISO dates (YYYY-MM-DD), years (YYYY), and partial dates.

    Args:
        date_str: Date string in various formats

    Returns:
        Year as string (YYYY)
    """
    if not is_valid(date_str):
        return ""

    date_str = str(date_str).strip()

    # Extract first 4 consecutive digits (year)
    import re

    match = re.search(r"\d{4}", date_str)
    if match:
        return match.group(0)

    return ""


def generate_citation_key(doi: str, row: pd.Series, used_keys: set) -> str:
    """
    Generate unique DOI-based citation key.

    Format: DOI with special chars replaced by underscores
    Example: "10.1021/acsomega.2c06948" -> "10_1021_acsomega_2c06948"

    Args:
        doi: DOI string
        row: Paper row data
        used_keys: Set of already-used keys (for collision detection)

    Returns:
        Unique citation key
    """
    base_key = None

    # Try DOI first (preferred)
    if is_valid(doi):
        doi = str(doi).strip()
        # Replace special characters with underscores
        base_key = doi.replace(".", "_").replace("/", "_")
        # Clean up multiple underscores
        while "__" in base_key:
            base_key = base_key.replace("__", "_")

    # Fallback: author-year format
    if not base_key:
        authors_str = safe_get(row, "authors")
        if is_valid(authors_str):
            # Get first author's last name
            first_author = str(authors_str).split(";")[0].strip()
            last_name = first_author.split()[-1] if first_author else "Unknown"
        else:
            last_name = "Unknown"

        year = extract_year(safe_get(row, "date"))
        title = safe_get(row, "title")
        first_word = str(title).split()[0] if is_valid(title) else "Paper"

        base_key = f"{last_name}{year}_{first_word}"

    # Ensure uniqueness
    final_key = base_key
    counter = 0
    while final_key in used_keys:
        counter += 1
        # Add suffix: a, b, c, etc.
        suffix = chr(ord("a") + (counter - 1))
        final_key = f"{base_key}_{suffix}"

    used_keys.add(final_key)
    return final_key


def format_bibtex_entry(row: pd.Series, citation_key: str) -> str:
    """
    Generate complete BibTeX entry for a paper.

    Args:
        row: Paper data row
        citation_key: Citation key for the entry

    Returns:
        Formatted BibTeX entry string
    """
    itemtype = safe_get(row, "itemType")
    entry_type = ITEMTYPE_TO_BIBTEX.get(itemtype, "misc")

    # Start entry
    lines = [f"@{entry_type}{{{citation_key},"]

    # Title (required)
    title = safe_get(row, "title")
    if is_valid(title):
        lines.append(f"  title = {{{escape_bibtex(title)}}},")

    # Author (required)
    authors_str = safe_get(row, "authors")
    if is_valid(authors_str):
        authors = format_authors(authors_str)
        lines.append(f"  author = {{{authors}}},")
    else:
        # BibTeX requires author or organization
        lines.append("  author = {Unknown},")

    # Year (required)
    date_str = safe_get(row, "date")
    year = extract_year(date_str)
    if year:
        lines.append(f"  year = {{{year}}},")

    # Journal (for articles)
    if entry_type == "article":
        journal = safe_get(row, "journalAbbreviation")
        if is_valid(journal):
            lines.append(f"  journal = {{{escape_bibtex(journal)}}},")

    # Booktitle (for inproceedings)
    if entry_type == "inproceedings":
        conference = safe_get(row, "conferenceName")
        if is_valid(conference):
            lines.append(f"  booktitle = {{{escape_bibtex(conference)}}},")

    # Volume
    volume = safe_get(row, "volume")
    if is_valid(volume):
        lines.append(f"  volume = {{{escape_bibtex(str(volume))}}},")

    # Issue/Number
    issue = safe_get(row, "issue")
    if is_valid(issue):
        lines.append(f"  number = {{{escape_bibtex(str(issue))}}},")

    # Pages
    pages = safe_get(row, "pages")
    if is_valid(pages):
        pages = format_pages(pages)
        lines.append(f"  pages = {{{pages}}},")

    # Publisher (for books, incollections)
    publisher = safe_get(row, "publisher")
    if is_valid(publisher) and entry_type in ["book", "incollection"]:
        lines.append(f"  publisher = {{{escape_bibtex(publisher)}}},")

    # DOI
    doi = safe_get(row, "DOI")
    if is_valid(doi):
        lines.append(f"  doi = {{{escape_bibtex(str(doi))}}},")

    # URL (landing page)
    url = safe_get(row, "url")
    if is_valid(url):
        lines.append(f"  url = {{{url}}},")

    # PDF file link (remote URL - no :PDF suffix needed for standard BibTeX)
    pdf_url = safe_get(row, "pdf_url")
    if is_valid(pdf_url):
        lines.append(f"  file = {{{pdf_url}}},")

    # Abstract (optional, but useful)
    abstract = safe_get(row, "abstract")
    if is_valid(abstract):
        # Escape and truncate if very long
        abstract_text = escape_bibtex(str(abstract))
        if len(abstract_text) > 500:
            abstract_text = abstract_text[:500] + "..."
        lines.append(f"  abstract = {{{abstract_text}}},")

    # Keywords (from HF tags) - standard BibTeX field
    tags_str = safe_get(row, "tags")
    if is_valid(tags_str):
        tags_list = parse_tags(tags_str)
        if tags_list:
            # Convert to comma-separated for BibTeX keywords field
            keywords = ", ".join(tags_list)
            lines.append(f"  keywords = {{{keywords}}},")

    # HuggingFace URL (in note field)
    hf_url = safe_get(row, "hf_url")
    if is_valid(hf_url):
        lines.append(f"  note = {{HuggingFace: {hf_url}}},")

    # GitHub repository (in howpublished field)
    github_repo = safe_get(row, "github_repo")
    if is_valid(github_repo):
        lines.append(f"  howpublished = {{{github_repo}}},")

    # Close entry (remove trailing comma from last line)
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")

    return "\n".join(lines)


def export_to_bibtex(data: pd.DataFrame, config: dict) -> str:
    """
    Export aggregated data to BibTeX file.

    Args:
        data: DataFrame with aggregated papers
        config: Configuration dictionary

    Returns:
        Path to generated BibTeX file
    """
    output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    dir_collect = os.path.join(output_dir, config["collect_name"])

    # Output file path
    output_file = os.path.join(dir_collect, "aggregated_results.bib")

    logger.info(f"Exporting {len(data)} papers to BibTeX")
    logger.info(f"Output file: {output_file}")

    entries = []
    used_keys = set()
    skipped = 0

    # Process each paper
    for row in data.itertuples(index=False):
        try:
            # Get citation key
            doi = safe_get(row, "DOI")
            citation_key = generate_citation_key(doi, row, used_keys)

            # Generate BibTeX entry
            entry = format_bibtex_entry(row, citation_key)
            entries.append(entry)

        except Exception as e:
            logger.warning(f"Error processing paper {safe_get(row, 'title')}: {e}")
            skipped += 1
            continue

    # Write to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(entries))
        f.write("\n")

    logger.info(f"Successfully exported {len(entries)} entries to {output_file}")
    if skipped > 0:
        logger.warning(f"Skipped {skipped} papers due to errors")

    return output_file


def main():
    """Main entry point for BibTeX export."""
    try:
        # Load configuration
        config = load_config()

        # Validate required config
        if "collect_name" not in config:
            raise ValueError("collect_name not specified in scilex.config.yml")

        # Load aggregated data
        data = load_aggregated_data(config)

        # Export to BibTeX
        output_file = export_to_bibtex(data, config)

        logger.info(f"BibTeX export complete: {output_file}")
        print(f"\n✓ BibTeX file created: {output_file}")

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during BibTeX export: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
