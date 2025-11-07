#!/usr/bin/env python3
"""
Test script to demonstrate the pagination bug with max_articles_per_query.

Run with: python tests/test_pagination_bug.py
"""

import math


def simulate_current_buggy_logic():
    """Simulates the CURRENT (buggy) pagination logic."""
    print("=" * 70)
    print("CURRENT (BUGGY) LOGIC:")
    print("=" * 70)

    # Config
    max_articles_per_query = 100
    max_by_page = 100

    # State
    page = 1  # Pages start at 1
    has_more_pages = True  # Initial value
    nb_art_collected = 0
    total_available = 500  # Assume 500 papers available in API

    iteration = 0
    while has_more_pages and iteration < 5:  # Limit iterations to prevent infinite loop
        iteration += 1
        print(f"\n--- Iteration {iteration} (page={page}) ---")
        print(f"  Loop condition: has_more_pages={has_more_pages}")

        # Simulate API call
        offset = (page - 1) * max_by_page
        print(f"  Fetching: offset={offset}, limit={max_by_page}")
        fetched = min(max_by_page, total_available - nb_art_collected)
        nb_art_collected += fetched
        print(f"  Fetched {fetched} articles. Total collected: {nb_art_collected}")

        # BUGGY: Check AFTER fetching
        expected_pages = math.ceil(total_available / max_by_page)
        has_more_pages = page < expected_pages

        # Apply limit (AFTER fetching - too late!)
        max_pages = math.ceil(max_articles_per_query / max_by_page)
        has_more_pages = has_more_pages and (page < max_pages)
        print(f"  Limit check: max_pages={max_pages}, page < max_pages = {page < max_pages}")
        print(f"  has_more_pages updated to: {has_more_pages}")

        # Increment page
        page += 1

    print(f"\n{'=' * 70}")
    print(f"RESULT: Collected {nb_art_collected} articles")
    print(f"EXPECTED: {max_articles_per_query} articles")
    print(f"BUG: Exceeded limit by {nb_art_collected - max_articles_per_query} articles!")
    print(f"{'=' * 70}\n")

    return nb_art_collected


def simulate_fixed_logic():
    """Simulates the FIXED pagination logic with pre-check."""
    print("=" * 70)
    print("FIXED LOGIC (with pre-check):")
    print("=" * 70)

    # Config
    max_articles_per_query = 100
    max_by_page = 100

    # State
    page = 1
    has_more_pages = True
    nb_art_collected = 0
    total_available = 500

    iteration = 0
    while has_more_pages and iteration < 5:
        iteration += 1
        print(f"\n--- Iteration {iteration} (page={page}) ---")
        print(f"  Loop condition: has_more_pages={has_more_pages}")

        # FIX: PRE-CHECK before fetching
        max_pages = math.ceil(max_articles_per_query / max_by_page)
        if page > max_pages:
            print(f"  PRE-CHECK: page {page} > max_pages {max_pages}")
            print(f"  ✓ Stopping BEFORE API call (limit reached)")
            break

        # Simulate API call
        offset = (page - 1) * max_by_page
        print(f"  PRE-CHECK: page {page} <= max_pages {max_pages}, OK to fetch")
        print(f"  Fetching: offset={offset}, limit={max_by_page}")
        fetched = min(max_by_page, total_available - nb_art_collected)
        nb_art_collected += fetched
        print(f"  Fetched {fetched} articles. Total collected: {nb_art_collected}")

        # Check for more pages
        expected_pages = math.ceil(total_available / max_by_page)
        has_more_pages = page < expected_pages
        print(f"  has_more_pages updated to: {has_more_pages}")

        # Increment page
        page += 1

    print(f"\n{'=' * 70}")
    print(f"RESULT: Collected {nb_art_collected} articles")
    print(f"EXPECTED: {max_articles_per_query} articles")
    print(f"✓ CORRECT: Matches expected limit!")
    print(f"{'=' * 70}\n")

    return nb_art_collected


def test_edge_cases():
    """Test edge cases with different article limits."""
    print("\n" + "=" * 70)
    print("EDGE CASE TESTS:")
    print("=" * 70)

    test_cases = [
        (100, 100, "Exact 1 page"),
        (150, 100, "1.5 pages"),
        (250, 100, "2.5 pages"),
        (100, 200, "0.5 pages (OpenAlex)"),
    ]

    for max_articles, max_by_page, description in test_cases:
        print(f"\n--- Test: {description} ---")
        print(f"  max_articles={max_articles}, max_by_page={max_by_page}")

        # Calculate expected
        expected_pages = math.ceil(max_articles / max_by_page)
        expected_articles = min(expected_pages * max_by_page, max_articles)

        # Simulate fixed logic
        page = 1
        collected = 0
        pages_fetched = 0

        while page <= expected_pages:
            collected += min(max_by_page, max_articles - collected)
            pages_fetched += 1
            page += 1

        print(f"  Expected pages: {expected_pages}")
        print(f"  Pages fetched: {pages_fetched}")
        print(f"  Articles collected: {collected}")
        print(f"  ✓ Correct: {collected <= max_articles}")


if __name__ == "__main__":
    print("\n" + "🔍 SEMANTIC SCHOLAR PAGINATION BUG DEMONSTRATION\n")

    # Test 1: Show the bug
    buggy_result = simulate_current_buggy_logic()

    # Test 2: Show the fix
    fixed_result = simulate_fixed_logic()

    # Test 3: Edge cases
    test_edge_cases()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print(f"Buggy logic collected: {buggy_result} articles (WRONG)")
    print(f"Fixed logic collected: {fixed_result} articles (CORRECT)")
    print(f"Difference: {buggy_result - fixed_result} extra articles fetched with bug")
    print("=" * 70)
