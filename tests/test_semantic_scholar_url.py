#!/usr/bin/env python3
"""
Test to verify Semantic Scholar URL construction with pagination parameters.
"""

from scilex.crawlers.collectors import SemanticScholar_collector


def test_semantic_scholar_url():
    """Test that Semantic Scholar URL has proper pagination parameters."""
    print("=" * 70)
    print("SEMANTIC SCHOLAR URL CONSTRUCTION TEST")
    print("=" * 70)

    # Create mock data_query
    data_query = {
        "year": 2024,
        "keyword": ["machine learning", "knowledge graph"],
        "max_articles_per_query": 100,
        "id_collect": 0,
        "total_art": 0,
        "last_page": 0,
        "coll_art": 0,
        "state": -1,
    }

    # Create collector
    collector = SemanticScholar_collector(
        data_query,
        "/tmp/test",
        None,  # No API key for this test
    )

    # Get URL
    url = collector.get_configurated_url()

    print(f"\nCollector: {collector.api_name}")
    print(f"max_by_page: {collector.max_by_page}")
    print(
        f"max_articles_per_query: {collector.filter_param.get_max_articles_per_query()}"
    )
    print("\nConstructed URL:")
    print(url)

    # Check for pagination parameters
    print(f"\n{'=' * 70}")
    print("VERIFICATION:")
    print("=" * 70)

    has_limit = "&limit=" in url
    has_offset = "&offset={}" in url

    print(f"✓ Has &limit= parameter: {has_limit}")
    print(f"✓ Has &offset={{}} placeholder: {has_offset}")

    if has_limit and has_offset:
        print("\n✅ URL IS CORRECT - has pagination parameters!")
    else:
        print("\n❌ URL IS BROKEN - missing pagination parameters!")
        if not has_limit:
            print("   Missing: &limit=100")
        if not has_offset:
            print("   Missing: &offset={}")

    # Show what the URL will look like with offsets
    print(f"\n{'=' * 70}")
    print("EXAMPLE PAGINATED URLS:")
    print("=" * 70)
    for page in [1, 2, 3]:
        offset = (page - 1) * collector.max_by_page
        paginated_url = url.format(offset)
        print(f"\nPage {page} (offset={offset}):")
        print(f"  {paginated_url[:100]}...")
        print(f"  ...&offset={offset}")


if __name__ == "__main__":
    test_semantic_scholar_url()
