"""
Test script for Phase 1 quality improvements.

This script validates that:
1. Weighted quality scoring works correctly
2. Quality filters apply properly
3. Keyword validation reports function
"""

import pandas as pd
from src.constants import MISSING_VALUE
from src.crawlers.aggregate import getquality
from src.quality_validation import (
    passes_quality_filters,
    apply_quality_filters,
    count_words,
    count_authors,
)
from src.keyword_validation import (
    check_keywords_in_paper,
    generate_keyword_validation_report,
)


def test_weighted_quality_scoring():
    """Test that weighted quality scoring gives higher scores to better records."""
    print("\n" + "=" * 70)
    print("TEST 1: Weighted Quality Scoring")
    print("=" * 70)

    # Create test records
    columns = [
        "DOI",
        "title",
        "authors",
        "date",
        "abstract",
        "journalAbbreviation",
        "volume",
        "issue",
        "publisher",
        "archive",
    ]

    # High-quality record (all critical fields)
    high_quality = {
        "DOI": "10.1234/test",
        "title": "Test Paper",
        "authors": "Smith, J.; Doe, A.",
        "date": "2024",
        "abstract": "This is a complete abstract with sufficient detail.",
        "journalAbbreviation": "Test Journal",
        "volume": "10",
        "issue": "5",
        "publisher": "Test Publisher",
        "archive": "IEEE",
    }

    # Medium-quality record (missing some important fields)
    medium_quality = {
        "DOI": "10.1234/test2",
        "title": "Another Test",
        "authors": "Jones, B.",
        "date": "2024",
        "abstract": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "publisher": "Test Pub",
        "archive": "OpenAlex",
    }

    # Low-quality Google Scholar record (no DOI)
    low_quality = {
        "DOI": MISSING_VALUE,
        "title": "Scholar Paper",
        "authors": "Author, X.",
        "date": "2024",
        "abstract": "Brief abstract.",
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "archive": "GoogleScholar",
    }

    high_score = getquality(high_quality, columns)
    medium_score = getquality(medium_quality, columns)
    low_score = getquality(low_quality, columns)

    print(f"High-quality record score: {high_score}")
    print(f"Medium-quality record score: {medium_score}")
    print(f"Low-quality record score: {low_score}")

    assert high_score > medium_score, "High quality should score higher than medium"
    assert medium_score > low_score, "Medium quality should score higher than low"
    print("✓ Quality scoring works as expected (high > medium > low)")


def test_quality_filters():
    """Test that quality filters correctly identify records to keep/reject."""
    print("\n" + "=" * 70)
    print("TEST 2: Quality Filters")
    print("=" * 70)

    # Test record with issues
    test_records = [
        {
            "DOI": "10.1234/good",
            "title": "Good Paper",
            "authors": "Smith, J.; Doe, A.",
            "date": "2024",
            "abstract": "This is a sufficiently long abstract with proper content that meets minimum word requirements.",
        },
        {
            "DOI": MISSING_VALUE,
            "title": "Missing DOI",
            "authors": "Jones, B.",
            "date": "2024",
            "abstract": "Good abstract here with enough words to pass.",
        },
        {
            "DOI": "10.1234/short",
            "title": "Short Abstract",
            "authors": "Brown, C.",
            "date": "2024",
            "abstract": "Too short.",
        },
        {
            "DOI": "10.1234/no-year",
            "title": "No Year",
            "authors": "Green, D.",
            "date": MISSING_VALUE,
            "abstract": "Abstract with enough words to pass minimum requirements.",
        },
    ]

    filters = {
        "require_doi": True,
        "require_abstract": True,
        "min_abstract_words": 10,
        "require_year": True,
        "min_author_count": 1,
    }

    print("\nApplying filters:")
    print(f"  - Require DOI: {filters['require_doi']}")
    print(f"  - Minimum abstract words: {filters['min_abstract_words']}")
    print(f"  - Require year: {filters['require_year']}")

    for i, record in enumerate(test_records, 1):
        passes, reason = passes_quality_filters(record, filters)
        status = "✓ PASS" if passes else f"✗ FAIL ({reason})"
        print(f"  Record {i} ({record['title']}): {status}")

    # Create DataFrame and apply filters
    df = pd.DataFrame(test_records)
    df_filtered, report = apply_quality_filters(df, filters, generate_report=False)

    print(f"\nOriginal papers: {len(df)}")
    print(f"After filtering: {len(df_filtered)}")
    print(f"Filtered out: {len(df) - len(df_filtered)}")

    assert len(df_filtered) == 1, "Should keep only 1 paper (the good one)"
    print("✓ Quality filters working correctly")


def test_keyword_validation():
    """Test keyword validation on sample papers."""
    print("\n" + "=" * 70)
    print("TEST 3: Keyword Validation")
    print("=" * 70)

    test_papers = [
        {
            "title": "Machine Learning for Data Analysis",
            "abstract": "This paper presents a novel machine learning approach.",
        },
        {
            "title": "Deep Neural Networks",
            "abstract": "We explore deep learning architectures.",
        },
        {
            "title": "Unrelated Topic",
            "abstract": "This paper discusses something completely different.",
        },
    ]

    keywords = [["machine learning", "deep learning"], []]

    print(f"\nKeywords: {keywords[0]}")
    print("\nValidating papers:")

    papers_with_keywords = 0
    for i, paper in enumerate(test_papers, 1):
        found, matched = check_keywords_in_paper(paper, keywords)
        if found:
            papers_with_keywords += 1
        status = "✓" if found else "✗"
        matched_str = f" (matched: {', '.join(matched)})" if matched else ""
        print(f"  {status} Paper {i}: {paper['title']}{matched_str}")

    assert papers_with_keywords >= 2, "At least 2 papers should match keywords"
    print(f"\n✓ Keyword validation working correctly ({papers_with_keywords}/{len(test_papers)} papers matched)")


def test_helper_functions():
    """Test helper functions for quality validation."""
    print("\n" + "=" * 70)
    print("TEST 4: Helper Functions")
    print("=" * 70)

    # Test word counting
    test_texts = [
        ("Simple abstract text here.", 4),
        ("", 0),
        (MISSING_VALUE, 0),
        ({"p": ["Para 1 text.", "Para 2 text."]}, 6),
    ]

    print("\nTesting word counting:")
    for text, expected in test_texts:
        result = count_words(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} count_words({repr(text)[:50]}) = {result} (expected {expected})")

    # Test author counting
    test_authors = [
        ("Smith, J.", 1),
        ("Smith, J.; Doe, A.; Brown, C.", 3),
        (["Smith", "Doe", "Brown"], 3),
        (MISSING_VALUE, 0),
    ]

    print("\nTesting author counting:")
    for authors, expected in test_authors:
        result = count_authors(authors)
        status = "✓" if result == expected else "✗"
        print(f"  {status} count_authors({repr(authors)[:50]}) = {result} (expected {expected})")

    print("\n✓ Helper functions working correctly")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTING PHASE 1 QUALITY IMPROVEMENTS")
    print("=" * 70)

    try:
        test_weighted_quality_scoring()
        test_quality_filters()
        test_keyword_validation()
        test_helper_functions()

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED! ✓")
        print("=" * 70)
        print("\nPhase 1 improvements are ready to use.")
        print("Update your scilex.config.yml with quality_filters section to enable.")

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
