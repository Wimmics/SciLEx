"""Simple Streamlit web interface for SciLEx."""

import contextlib
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import yaml

from scilex.config_defaults import DEFAULT_OUTPUT_DIR
from scilex.constants import is_valid

# Add src/ to path for SciLEx imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
API_CONFIG_PATH = PROJECT_ROOT / "scilex" / "api.config.yml"


def get_available_collections(base_dir: str) -> dict[str, int | None]:
    """Scan output directory and return {name: paper_count} for each collection.

    Returns paper count from aggregated CSV when available, or ``None``
    for collections that were started but not yet aggregated (partial/interrupted).
    Uses line counting instead of loading CSVs for performance.
    """
    output_path = Path(base_dir)
    collections: dict[str, int | None] = {}
    if not output_path.exists():
        return collections
    for item in output_path.iterdir():
        if item.is_dir() and item.name not in ["text_to_sparql", "text2sparql"]:
            csv_path = item / "aggregated_results.csv"
            if csv_path.exists():
                # Count lines minus header for paper count
                with csv_path.open() as f:
                    count = sum(1 for _ in f) - 1
                collections[item.name] = max(count, 0)
            elif any(item.iterdir()):
                # Directory has files but no aggregated CSV yet (partial run)
                collections[item.name] = None
    return collections


def load_local_api_config() -> dict:
    """Load locally stored API configuration for pre-filling sidebar fields."""
    if not API_CONFIG_PATH.exists():
        return {}
    try:
        with API_CONFIG_PATH.open() as config_file:
            return yaml.safe_load(config_file) or {}
    except Exception:
        return {}


# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="SciLEx - Paper Collection Interface",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
    .main {
        max-width: 1200px;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.1em;
        font-weight: 600;
    }
    .metric-card {
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        background-color: #f0f2f6;
    }
    .success-card {
        padding: 20px;
        border-radius: 10px;
        background-color: #d4edda;
        border-left: 4px solid #28a745;
    }
    .error-card {
        padding: 20px;
        border-radius: 10px;
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# SIDEBAR - CONFIG & NAVIGATION
# ============================================================================

with st.sidebar.expander("⚙️ Configuration", expanded=True):
    api_base_url = st.text_input(
        "API Backend URL",
        value="http://localhost:8000",
        help="FastAPI backend URL used by the web interface",
    )

    # API Keys — grouped by category
    st.subheader("🔑 API Keys")
    saved_api_config = load_local_api_config()

    free_api_options = {
        "SemanticScholar": {"api_key": "API Key"},
        "OpenAlex": {"api_key": "API Key (optional, higher rate limits)"},
        "PubMed": {"api_key": "API Key (optional, higher rate limits)"},
        "CrossRef": {"mailto": "Email (for polite pool)"},
    }

    paid_api_options = {
        "IEEE": {"api_key": "API Key"},
        "Elsevier": {
            "api_key": "API Key",
            "inst_token": "Institutional Token",
        },
        "Springer": {"api_key": "API Key"},
    }

    integration_options = {
        "Zotero": {
            "api_key": "API Key",
            "user_id": "User ID",
            "user_mode": "User Mode (user/group)",
        },
        "HuggingFace": {"token": "Access Token"},
    }

    def _render_api_group(api_group: dict) -> None:
        """Render API key inputs for a group of APIs."""
        for api_name, fields in api_group.items():
            api_saved = saved_api_config.get(api_name, {})
            is_configured = any(api_saved.get(f) for f in fields)

            symbol, color, weight = (
                ("●", "#28a745", 600) if is_configured else ("○", "#999", 400)
            )
            st.markdown(
                f"<span style='color: {color}; font-weight: {weight};'>{symbol} {api_name}</span>",
                unsafe_allow_html=True,
            )

            current_input_values = {}
            for field_name, field_label in fields.items():
                default_value = str(api_saved.get(field_name, "") or "")
                if (
                    api_name == "Zotero"
                    and field_name == "user_mode"
                    and not default_value
                ):
                    default_value = "user"
                current_input_values[field_name] = st.text_input(
                    field_label,
                    type="password",
                    value=default_value,
                    key=f"api_{api_name}_{field_name}",
                )

            col_save, col_delete = st.columns(2)

            if col_save.button("💾 Save", key=f"save_{api_name}"):
                payload = {"api_name": api_name}
                for field_name in fields:
                    field_value = current_input_values.get(field_name, "")
                    if field_value:
                        payload[field_name] = field_value

                if len(payload) == 1:
                    st.warning("Provide at least one credential.")
                else:
                    try:
                        response = requests.post(
                            f"{api_base_url.rstrip('/')}/api-config",
                            json=payload,
                            timeout=20,
                        )
                        if response.status_code == 200:
                            st.success(f"{api_name} saved.")
                        else:
                            try:
                                error_detail = response.json().get(
                                    "detail", response.text
                                )
                            except Exception:
                                error_detail = response.text
                            st.error(f"Failed ({response.status_code}): {error_detail}")
                    except requests.RequestException as exc:
                        st.error(f"Backend unreachable: {exc}")

            if col_delete.button("🗑️ Clear", key=f"delete_{api_name}"):
                for field_name in fields:
                    with contextlib.suppress(requests.RequestException):
                        requests.delete(
                            f"{api_base_url.rstrip('/')}/api-config/{api_name}/{field_name}",
                            timeout=20,
                        )
                st.success(f"{api_name} credentials cleared.")
                st.rerun()

            st.divider()

    with st.expander("🆓 Free APIs", expanded=False):
        _render_api_group(free_api_options)

    with st.expander("💳 Paid APIs", expanded=False):
        _render_api_group(paid_api_options)

    with st.expander("🔌 Integrations", expanded=False):
        _render_api_group(integration_options)

    # Output directory
    output_dir = st.text_input(
        "Output Directory",
        value=DEFAULT_OUTPUT_DIR,
        help=(
            "Base folder for all results. Each collection creates its own subfolder.\n"
            "Use an absolute path for consistency across runs."
        ),
    )

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.title("📚 SciLEx - Paper Collection & Analysis Platform")

st.markdown(
    """
    **SciLEx** is a comprehensive tool for systematically collecting, aggregating, and analyzing academic papers.

    This interface lets you search multiple academic databases, filter results, and export your findings in multiple formats.
    """
)

# ============================================================================
# TABS
# ============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🔬 New Collection",
        "📊 View Results",
        "🔍 Filter & Export",
        "📈 Collections History",
        "ℹ️ Help",
    ]
)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: NEW COLLECTION
# ═══════════════════════════════════════════════════════════════════════════

with tab1:
    st.header("Start a New Collection")
    st.markdown(
        "Configure and launch a new paper collection workflow from multiple academic databases."
    )

    # Load last-used config as defaults
    _prev_config: dict = {}
    _prev_config_path = PROJECT_ROOT / "scilex" / "scilex.config.yml"
    if _prev_config_path.exists():
        with open(_prev_config_path) as _f:
            _prev_config = yaml.safe_load(_f) or {}
    _prev_qf = _prev_config.get("quality_filters", {})

    # Extract previous keywords as newline-separated text
    _prev_kw = _prev_config.get("keywords", [])
    _prev_kw1 = "\n".join(_prev_kw[0]) if _prev_kw else ""
    _prev_kw2 = "\n".join(_prev_kw[1]) if len(_prev_kw) > 1 else ""

    # Extract previous API selections
    _prev_apis = _prev_config.get("apis", [])
    _all_free = [
        "SemanticScholar",
        "OpenAlex",
        "Arxiv",
        "PubMed",
        "PubMedCentral",
        "DBLP",
        "HAL",
        "Istex",
    ]
    _all_paid = ["IEEE", "Elsevier", "Springer"]
    _prev_free = [a for a in _prev_apis if a in _all_free] or [
        "SemanticScholar",
        "OpenAlex",
        "Arxiv",
    ]
    _prev_paid = [a for a in _prev_apis if a in _all_paid]

    with st.form("collection_form"):
        st.subheader("1️⃣ Search Parameters")

        col1, col2 = st.columns(2)

        with col1:
            collect_name = st.text_input(
                "Collection Name",
                value=_prev_config.get("collect_name", "my_research_"),
                help=(
                    "Becomes the output subfolder name (e.g. output/my_research_).\n"
                    "Re-using an existing name lets you resume a partial collection."
                ),
            )
            years = st.multiselect(
                "Publication Years",
                options=list(range(2026, 2000, -1)),
                default=_prev_config.get("years", [2025, 2026]),
                help=(
                    "Only papers published in these years will be collected.\n"
                    "Papers outside this range are filtered out during aggregation."
                ),
            )

        with col2:
            _ss_modes = ["regular", "bulk"]
            _ss_prev = _prev_config.get("semantic_scholar_mode", "regular")
            semantic_scholar_mode = st.selectbox(
                "Semantic Scholar Mode",
                _ss_modes,
                index=_ss_modes.index(_ss_prev) if _ss_prev in _ss_modes else 0,
                help=(
                    "regular: Standard search, 100 papers per request (recommended).\n"
                    "bulk: 1000 papers per request, much faster but requires "
                    "Semantic Scholar API approval."
                ),
            )
            aggregate_citations = st.checkbox(
                "Fetch Citation Counts",
                value=_prev_config.get("aggregate_get_citations", True),
                help=(
                    "Fetches citation counts "
                    "(cache → Semantic Scholar → CrossRef → OpenCitations).\n"
                    "Enables time-aware citation filtering "
                    "(e.g. ≥1 citation after 18 months)."
                ),
            )
            enable_enrichment = st.checkbox(
                "Enable HuggingFace Enrichment",
                value=_prev_config.get("enable_enrichment", False),
                help=(
                    "Detects ML/AI papers with linked models, datasets, "
                    "and GitHub repos on HuggingFace.\n"
                    "Rate-limited: 5 req/sec with API token, 1 req/sec without."
                ),
            )

        st.subheader("2️⃣ Keywords")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Primary Keywords Group**")
            keywords_group1 = st.text_area(
                "Primary keywords (one per line)",
                value=_prev_kw1,
                help=(
                    "Papers must contain at least ONE of these keywords (OR logic).\n"
                    "Case-insensitive matching against title and abstract."
                ),
                key="keywords1",
            )

        with col2:
            st.write("**Secondary Keywords Group (Optional)**")
            keywords_group2 = st.text_area(
                "Secondary keywords (one per line, or leave empty)",
                value=_prev_kw2,
                help=(
                    "Papers must match at least one keyword from EACH group "
                    "(AND between groups, OR within).\n"
                    "Leave empty to use only primary keywords."
                ),
                key="keywords2",
            )

        _prev_bonus = _prev_config.get("bonus_keywords", [])
        bonus_keywords_text = st.text_area(
            "Bonus Keywords (Optional)",
            value="\n".join(_prev_bonus) if _prev_bonus else "",
            help=(
                "Increase a paper's relevance score during ranking, "
                "but never exclude papers.\n"
                "Useful for related terms that indicate quality "
                "without being required."
            ),
            key="bonus_keywords",
        )

        st.subheader("3️⃣ Data Sources")

        col1, col2 = st.columns(2)

        with col1:
            free_apis = st.multiselect(
                "Free APIs",
                options=_all_free,
                default=_prev_free,
                key="free_apis",
                help=(
                    "Academic databases that don't require API keys.\n"
                    "Using multiple sources improves coverage; "
                    "duplicates are removed automatically."
                ),
            )

        with col2:
            paid_apis = st.multiselect(
                "Paid APIs (requires key)",
                options=_all_paid,
                default=_prev_paid,
                key="paid_apis",
                help=(
                    "Require an API key configured in the sidebar.\n"
                    "IEEE covers engineering; "
                    "Elsevier and Springer cover broad science."
                ),
            )

        selected_apis = free_apis + paid_apis

        st.subheader("4️⃣ Quality Filters")

        # Defaults used when advanced filters are hidden
        min_abstract = _prev_qf.get("min_abstract_words", 50)
        max_abstract = _prev_qf.get("max_abstract_words", 1000)
        enable_base_filters = _prev_qf.get("enable_text_filter", True)
        allowed_types = _prev_qf.get(
            "allowed_item_types", ["journalArticle", "conferencePaper"]
        ) or ["journalArticle", "conferencePaper"]
        apply_relevance = _prev_qf.get("apply_relevance_ranking", True)

        with st.expander("Advanced quality filters", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                enable_base_filters = st.checkbox(
                    "Enable Base Filters",
                    value=enable_base_filters,
                    help=(
                        "Requires DOI, abstract, publication year, "
                        "and at least 2 authors.\n"
                        "Also applies abstract length checks. "
                        "Disable for exploratory searches."
                    ),
                )

                if enable_base_filters:
                    min_abstract = st.slider(
                        "Minimum Abstract Length (words)",
                        min_value=0,
                        max_value=500,
                        value=min_abstract,
                        help=(
                            "Detects truncated or stub abstracts. "
                            "Typical range: 50–100 words.\n"
                            "Set to 0 to disable this check."
                        ),
                    )
                    max_abstract = st.slider(
                        "Maximum Abstract Length (words)",
                        min_value=100,
                        max_value=2000,
                        value=max_abstract,
                        help=(
                            "Detects copy-paste errors or non-abstract text. "
                            "Typical range: 500–1000.\n"
                            "Set to the maximum to effectively disable."
                        ),
                    )

            with col2:
                allowed_types = st.multiselect(
                    "Allowed Publication Types",
                    options=[
                        "journalArticle",
                        "conferencePaper",
                        "bookSection",
                        "book",
                        "preprint",
                    ],
                    default=allowed_types,
                    help=(
                        "Whitelist: only papers matching these types are kept.\n"
                        "journalArticle and conferencePaper cover "
                        "most peer-reviewed work."
                    ),
                )

            apply_relevance = st.checkbox(
                "Sort by Relevance Score",
                value=apply_relevance,
                help=(
                    "Composite 0–10 score: keyword density (45%), "
                    "metadata completeness (25%),\n"
                    "publication venue (20%), citations (10%).\n"
                    "Disable to keep papers in their original collection order."
                ),
            )

        st.subheader("5️⃣ Maximum Papers")
        max_papers = st.number_input(
            "Maximum Papers to Keep",
            min_value=10,
            max_value=10000,
            value=_prev_qf.get("max_papers", 500),
            step=50,
            help=(
                "Final cap applied after all filtering and ranking.\n"
                "500–1000 for a focused review, "
                "higher for comprehensive surveys."
            ),
        )

        # Parse keywords
        keywords_list = [[k.strip() for k in keywords_group1.split("\n") if k.strip()]]
        if keywords_group2.strip():
            keywords_list.append(
                [k.strip() for k in keywords_group2.split("\n") if k.strip()]
            )

        bonus_keywords = [
            k.strip() for k in bonus_keywords_text.split("\n") if k.strip()
        ]

        submitted = st.form_submit_button(
            "Start Collection",
            width="stretch",
            type="primary",
        )

        if submitted:
            # Validation
            if not collect_name.strip():
                st.error("❌ Please enter a collection name")
            elif not keywords_list[0]:
                st.error("❌ Please enter at least one primary keyword")
            elif not selected_apis:
                st.error("❌ Please select at least one data source")
            elif not years:
                st.error("❌ Please select at least one year")
            else:
                # Check if this collection already has data
                collect_path = Path(output_dir) / collect_name
                has_results = collect_path.exists() and any(collect_path.iterdir())

                if has_results:
                    has_aggregated = (collect_path / "aggregated_results.csv").exists()
                    if has_aggregated:
                        st.info(
                            "A collection with this name already has completed results. "
                            "Resubmitting will skip already-collected queries. "
                            "To start a fresh collection, use a different name."
                        )
                    else:
                        st.warning(
                            "A collection with this name has partial data from a "
                            "previous run. Submitting will resume where it left off. "
                            "To start fresh, use a different name."
                        )

                request_payload = {
                    "collection_config": {
                        "keywords": keywords_list,
                        "bonus_keywords": bonus_keywords,
                        "years": years,
                        "apis": selected_apis,
                        "collect_name": collect_name,
                        "semantic_scholar_mode": semantic_scholar_mode,
                        "aggregate_get_citations": aggregate_citations,
                        "output_dir": output_dir,
                        "enable_enrichment": enable_enrichment,
                    },
                    "api_config": load_local_api_config(),
                    "quality_filters": {
                        "enable_text_filter": enable_base_filters,
                        "min_abstract_words": int(min_abstract),
                        "max_abstract_words": int(max_abstract),
                        "enable_itemtype_bypass": not bool(allowed_types),
                        "enable_itemtype_filter": bool(allowed_types),
                        "allowed_item_types": allowed_types or None,
                        "apply_relevance_ranking": apply_relevance,
                        "max_papers": int(max_papers),
                    },
                }

                try:
                    response = requests.post(
                        f"{api_base_url.rstrip('/')}/pipelines/start",
                        json=request_payload,
                        timeout=30,
                    )

                    if response.status_code == 200:
                        response_data = response.json()
                        job_id = response_data.get("job_id")

                        st.success(
                            f"""
                            ✅ Pipeline started successfully!

                            **Summary:**
                            - Job ID: {job_id}
                            - Keywords: {len(keywords_list)} group(s)
                            - Years: {len(years)} year(s) selected
                            - APIs: {len(selected_apis)} source(s)
                            - Max papers: {max_papers}
                            """
                        )

                        st.session_state["pipeline_started"] = True
                        st.session_state["pipeline_job_id"] = job_id
                        st.session_state["collection_config"] = {
                            "keywords": keywords_list,
                            "bonus_keywords": bonus_keywords,
                            "years": years,
                            "apis": selected_apis,
                            "collect_name": collect_name,
                            "semantic_scholar_mode": semantic_scholar_mode,
                            "aggregate_get_citations": aggregate_citations,
                            "output_dir": output_dir,
                            "enable_enrichment": enable_enrichment,
                        }
                    else:
                        try:
                            error_detail = response.json().get("detail", response.text)
                        except Exception:
                            error_detail = response.text
                        st.error(
                            f"❌ Failed to start pipeline ({response.status_code}): {error_detail}"
                        )

                except requests.RequestException as exc:
                    st.error(
                        f"❌ Could not reach backend at {api_base_url}. Error: {exc}"
                    )

    # ── Pipeline Progress Monitor ──
    if st.session_state.get("pipeline_job_id"):
        st.write("---")
        st.subheader("Pipeline Progress")
        job_id = st.session_state["pipeline_job_id"]

        try:
            resp = requests.get(
                f"{api_base_url.rstrip('/')}/pipelines/{job_id}/status",
                timeout=5,
            )

            if resp.status_code == 404:
                st.warning(
                    "Job not found — the backend may have restarted. "
                    "Clearing stale job reference."
                )
                del st.session_state["pipeline_job_id"]
                st.rerun()

            data = resp.json()

            # ── Phase stepper (dynamic based on enrichment) ──
            enrichment_enabled = data.get("enrichment_enabled", False)
            phases = ["Initializing", "Collecting", "Aggregating"]
            if enrichment_enabled:
                phases.append("Enriching")
            phases.append("Completed")

            phase_map = {p.lower(): i for i, p in enumerate(phases)}
            # "enriching" maps to "aggregating" when enrichment is disabled
            if not enrichment_enabled:
                phase_map["enriching"] = phase_map["aggregating"]
            current_phase_idx = phase_map.get(data.get("phase", "initializing"), 0)
            step_cols = st.columns(len(phases))
            for i, phase_label in enumerate(phases):
                with step_cols[i]:
                    if i < current_phase_idx:
                        st.markdown(f"✅ **{phase_label}**")
                    elif i == current_phase_idx:
                        st.markdown(f"🔵 **{phase_label}**")
                    else:
                        st.markdown(f"⚪ {phase_label}")

            # Show progress bar
            progress_value = max(0, min(data.get("progress", 0), 100))

            st.progress(
                progress_value / 100,
                text=data.get("message", ""),
            )

            # Show per-API stats if available
            api_stats = data.get("api_stats")
            if api_stats:
                cols = st.columns(min(len(api_stats), 4))
                for idx, (api_name, stats) in enumerate(api_stats.items()):
                    with cols[idx % len(cols)]:
                        completed = stats.get("completed", 0)
                        total = stats.get("total", 0)
                        articles = stats.get("articles", 0)
                        st.metric(
                            api_name,
                            f"{articles} papers",
                            delta=f"{completed}/{total} queries",
                        )

            # Pipeline log viewer
            logs = data.get("logs", [])
            if logs:
                with st.expander("📋 Pipeline Logs", expanded=False):
                    st.code("\n".join(logs[-100:]), language="text")

            # Terminal states
            status = data.get("status")
            if status in ("completed", "failed", "cancelled"):
                if status == "completed":
                    st.success("Pipeline completed successfully!")

                    # ── Filtering pipeline summary ──
                    filtering_summary = data.get("filtering_summary")
                    if filtering_summary:
                        with st.expander(
                            "🔬 Filtering Pipeline Summary", expanded=True
                        ):
                            # Summary metrics row
                            fs1, fs2, fs3 = st.columns(3)
                            initial = filtering_summary.get("initial_count", 0)
                            final = filtering_summary.get("final_count", 0)
                            retention = (final / initial * 100) if initial > 0 else 0
                            with fs1:
                                st.metric("Started With", f"{initial:,}")
                            with fs2:
                                st.metric("Final Output", f"{final:,}")
                            with fs3:
                                st.metric("Retention Rate", f"{retention:.1f}%")

                            # Stage-by-stage table
                            stages = filtering_summary.get("stages", [])
                            if stages:
                                table_data = [
                                    {
                                        "Stage": s.get("stage", "Unknown"),
                                        "Description": s.get("description", ""),
                                        "Papers": s.get("papers", 0),
                                        "Removed": s.get("removed", 0),
                                        "Removal %": f"{s.get('removal_rate', 0.0):.1f}%",
                                    }
                                    for s in stages
                                ]
                                st.dataframe(
                                    pd.DataFrame(table_data),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                    stats = data.get("stats")
                    if stats:
                        # Metric cards
                        mc1, mc2, mc3 = st.columns(3)
                        with mc1:
                            st.metric("📄 Total Papers", stats.get("total_papers", 0))
                        with mc2:
                            by_year = stats.get("by_year", {})
                            if by_year:
                                years_sorted = sorted(by_year.keys())
                                st.metric(
                                    "📅 Year Range",
                                    f"{years_sorted[0]}–{years_sorted[-1]}",
                                )
                            else:
                                st.metric("📅 Year Range", "—")
                        with mc3:
                            # Count unique base API names
                            by_source_raw = stats.get("by_source", {})
                            unique_apis = {
                                part.strip().rstrip("*")
                                for name in by_source_raw
                                for part in str(name).split(";")
                                if part.strip().rstrip("*")
                            }
                            st.metric("🗂️ Sources", len(unique_apis))

                        # Mini bar chart of sources (aggregate by base API name)
                        by_source = stats.get("by_source", {})
                        if by_source:
                            from collections import Counter

                            source_counts: Counter[str] = Counter()
                            for composite_name, count in by_source.items():
                                # Extract individual API names from composite
                                # e.g. "OpenAlex*;SemanticScholar*" → ["OpenAlex", "SemanticScholar"]
                                for part in str(composite_name).split(";"):
                                    base_name = part.strip().rstrip("*")
                                    if base_name:
                                        source_counts[base_name] += count
                            source_df = pd.DataFrame(
                                list(source_counts.items()),
                                columns=["Source", "Papers"],
                            ).set_index("Source")
                            st.bar_chart(source_df)

                        st.info(
                            "Switch to the **📊 View Results** tab above "
                            "to browse papers and see detailed statistics."
                        )
                elif status == "cancelled":
                    st.warning(
                        "Pipeline was cancelled. You can restart with the same "
                        "collection name — completed queries will be skipped."
                    )
                elif status == "failed":
                    st.error(f"Pipeline failed: {data.get('error', 'Unknown error')}")
                del st.session_state["pipeline_job_id"]
            else:
                # Cancel button
                if st.button("⏹️ Cancel Pipeline", type="secondary"):
                    try:
                        requests.post(
                            f"{api_base_url.rstrip('/')}/pipelines/{job_id}/cancel",
                            timeout=5,
                        )
                        st.warning("Cancellation requested...")
                    except requests.RequestException:
                        st.error("Could not reach backend to cancel.")

                # Auto-refresh
                time.sleep(2)
                st.rerun()

        except requests.RequestException:
            st.warning("Cannot reach backend, retrying...")
            time.sleep(3)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: VIEW RESULTS
# ═══════════════════════════════════════════════════════════════════════════

with tab2:
    st.header("View Collection Results")

    # Use shared collection helper
    output_path = Path(output_dir)
    collections_with_counts = get_available_collections(output_dir)

    if not collections_with_counts:
        st.info(
            "📭 No collections found. Start a new collection in the **New Collection** tab."
        )
    else:
        collection_names = list(collections_with_counts.keys())
        selected_collection = st.selectbox(
            "Select a Collection",
            collection_names,
            key="view_collection",
            format_func=lambda x: (
                f"📦 {x} ({collections_with_counts[x]} papers)"
                if collections_with_counts.get(x) is not None
                else f"📦 {x} (partial)"
            ),
        )

        # Sync selection to shared session state
        st.session_state["selected_collection"] = selected_collection

        if collections_with_counts.get(selected_collection) is None:
            st.warning(
                "This collection has partial data and no aggregated results yet. "
                "Resume or re-run the collection pipeline first."
            )
            st.stop()

        csv_path = output_path / selected_collection / "aggregated_results.csv"

        try:
            df = pd.read_csv(csv_path, delimiter=";")

            # Derive year from date if year column is missing
            if "year" not in df.columns and "date" in df.columns:
                df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("📄 Total Papers", len(df))

            with col2:
                if "year" in df.columns:
                    st.metric("📅 Years", f"{df['year'].min()}-{df['year'].max()}")

            with col3:
                if "archive" in df.columns:
                    st.metric("🗂️ Sources", df["archive"].nunique())

            with col4:
                if "nb_citation" in df.columns:
                    st.metric("📚 Avg Citations", f"{df['nb_citation'].mean():.1f}")

            st.write("---")

            # Display statistics
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Papers by Year")
                if "year" in df.columns:
                    year_counts = df["year"].value_counts().sort_index()
                    st.bar_chart(year_counts)

            with col2:
                st.subheader("Papers by Source")
                if "archive" in df.columns:
                    # Aggregate by base API name (strip * and split ;)
                    base_sources = (
                        df["archive"]
                        .fillna("")
                        .str.split(";")
                        .explode()
                        .str.strip()
                        .str.rstrip("*")
                    )
                    base_sources = base_sources[base_sources != ""]
                    st.bar_chart(base_sources.value_counts())

            st.write("---")

            # Display papers table
            st.subheader("Papers List")

            # Allow pagination
            if "page" not in st.session_state:
                st.session_state.page = 0

            rows_per_page = 20
            total_pages = (len(df) + rows_per_page - 1) // rows_per_page

            col1, col2, col3 = st.columns([1, 2, 1])

            with col1:
                if (
                    st.button("⬅️ Previous", width="stretch")
                    and st.session_state.page > 0
                ):
                    st.session_state.page -= 1

            with col2:
                page = st.selectbox(
                    "Page",
                    range(total_pages),
                    index=st.session_state.page,
                    label_visibility="collapsed",
                )
                st.session_state.page = page
                st.write(f"Page {page + 1} of {total_pages}")

            with col3:
                if (
                    st.button("Next ➡️", width="stretch")
                    and st.session_state.page < total_pages - 1
                ):
                    st.session_state.page += 1

            start_idx = st.session_state.page * rows_per_page
            end_idx = start_idx + rows_per_page

            display_df = df.iloc[start_idx:end_idx].copy()

            # Build clickable link column from DOI or url
            def _make_link(row):
                if "DOI" in row.index and is_valid(row.get("DOI")):
                    doi = str(row["DOI"])
                    if not doi.startswith("http"):
                        doi = f"https://doi.org/{doi}"
                    return doi
                if "url" in row.index and is_valid(row.get("url")):
                    return str(row["url"])
                return None

            display_df["link"] = display_df.apply(_make_link, axis=1)

            # Columns to display (abstract removed — shown in detail card below)
            display_columns = [
                col
                for col in [
                    "title",
                    "link",
                    "authors",
                    "year",
                    "archive",
                    "nb_citation",
                ]
                if col in display_df.columns
            ]

            selection = st.dataframe(
                display_df[display_columns],
                width="stretch",
                height=400,
                column_config={
                    "link": st.column_config.LinkColumn(
                        "Link", display_text="Open", width="small"
                    ),
                },
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
            )

            # Detail card on row selection
            selected_rows = selection.selection.rows  # type: ignore[union-attr]
            if selected_rows:
                sel_idx = selected_rows[0]
                paper = display_df.iloc[sel_idx]
                with st.container(border=True):
                    st.subheader(str(paper.get("title", "Untitled")))
                    detail_cols = st.columns([2, 1])
                    with detail_cols[0]:
                        if "authors" in paper.index and is_valid(paper.get("authors")):
                            st.markdown(f"**Authors:** {paper['authors']}")
                        if "abstract" in paper.index and is_valid(
                            paper.get("abstract")
                        ):
                            st.markdown("**Abstract:**")
                            st.write(str(paper["abstract"]))
                    with detail_cols[1]:
                        if "year" in paper.index:
                            st.metric("Year", paper["year"])
                        if "nb_citation" in paper.index:
                            st.metric("Citations", paper["nb_citation"])
                        if "relevance_score" in paper.index:
                            st.metric("Relevance", f"{paper['relevance_score']:.1f}/10")
                        link = paper.get("link")
                        if link:
                            st.link_button("Open Paper →", str(link))

        except Exception as e:
            st.error(f"Error loading results: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: FILTER & EXPORT
# ═══════════════════════════════════════════════════════════════════════════

with tab3:
    st.header("Filter & Export Results")

    # Reuse shared collection helper
    collections_with_counts_t3 = get_available_collections(output_dir)
    output_path = Path(output_dir)

    if not collections_with_counts_t3:
        st.info("📭 No collections found.")
    else:
        collection_names_t3 = list(collections_with_counts_t3.keys())
        # Default to the same collection selected in Tab 2 if available
        default_idx = 0
        shared = st.session_state.get("selected_collection")
        if shared and shared in collection_names_t3:
            default_idx = collection_names_t3.index(shared)

        selected_collection = st.selectbox(
            "Select a Collection",
            collection_names_t3,
            index=default_idx,
            key="export_collection",
            format_func=lambda x: (
                f"📦 {x} ({collections_with_counts_t3[x]} papers)"
                if collections_with_counts_t3.get(x) is not None
                else f"📦 {x} (partial)"
            ),
        )

        if collections_with_counts_t3.get(selected_collection) is None:
            st.warning(
                "This collection has partial data and no aggregated results yet. "
                "Resume or re-run the collection pipeline first."
            )
            st.stop()

        csv_path = output_path / selected_collection / "aggregated_results.csv"

        try:
            df = pd.read_csv(csv_path, delimiter=";")

            # Derive year from date if year column is missing
            if "year" not in df.columns and "date" in df.columns:
                df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year

            # Create filter panel
            st.subheader("🔍 Filters")

            with st.form("filter_form"):
                col1, col2 = st.columns(2)

                with col1:
                    # Year filter
                    if "year" in df.columns:
                        years_available = sorted(df["year"].unique())
                        year_range = st.slider(
                            "Year Range",
                            min_value=int(min(years_available)),
                            max_value=int(max(years_available)),
                            value=(
                                int(min(years_available)),
                                int(max(years_available)),
                            ),
                        )
                        df = df[
                            (df["year"] >= year_range[0])
                            & (df["year"] <= year_range[1])
                        ]

                    # Source filter (show base API names, not composite archive strings)
                    if "archive" in df.columns:
                        all_base_sources = sorted(
                            {
                                part.strip().rstrip("*")
                                for val in df["archive"].dropna().unique()
                                for part in str(val).split(";")
                                if part.strip().rstrip("*")
                            }
                        )
                        selected_sources = st.multiselect(
                            "Sources",
                            options=all_base_sources,
                            default=all_base_sources,
                        )
                        if selected_sources:
                            # Keep rows where archive contains any selected source
                            mask = (
                                df["archive"]
                                .fillna("")
                                .apply(
                                    lambda x: any(
                                        s
                                        in {
                                            p.strip().rstrip("*")
                                            for p in str(x).split(";")
                                        }
                                        for s in selected_sources
                                    )
                                )
                            )
                            df = df[mask]

                with col2:
                    # Citation filter
                    if "nb_citation" in df.columns:
                        citation_range = st.slider(
                            "Citation Range",
                            min_value=0,
                            max_value=int(df["nb_citation"].max()),
                            value=(0, int(df["nb_citation"].max())),
                        )
                        df = df[
                            (df["nb_citation"] >= citation_range[0])
                            & (df["nb_citation"] <= citation_range[1])
                        ]

                    # Abstract length filter
                    if "abstract" in df.columns:
                        df["abstract_length"] = (
                            df["abstract"].fillna("").str.split().str.len()
                        )
                        min_words, max_words = st.slider(
                            "Abstract Length (words)",
                            min_value=0,
                            max_value=int(df["abstract_length"].max()),
                            value=(50, int(df["abstract_length"].max())),
                        )
                        df = df[
                            (df["abstract_length"] >= min_words)
                            & (df["abstract_length"] <= max_words)
                        ]

                apply_filters = st.form_submit_button(
                    "✅ Apply Filters",
                    width="stretch",
                    type="primary",
                )

            st.success(f"✅ Filtered to {len(df)} papers")

            # Export options
            st.subheader("📥 Export Options")

            col1, col2, col3 = st.columns(3)

            # Prepare export data eagerly (df is already loaded)
            csv_content = df.to_csv(index=False, sep=";")
            json_content = df.to_json(orient="records", indent=2)

            with col1:
                st.download_button(
                    label="📊 Download as CSV",
                    data=csv_content.encode(),
                    file_name=f"{selected_collection}_filtered.csv",
                    mime="text/csv",
                    width="stretch",
                )

            with col2:
                # BibTeX requires generation — check if file exists already
                bib_file_path = (
                    output_path / selected_collection / "aggregated_results.bib"
                )
                if bib_file_path.exists():
                    bib_content = bib_file_path.read_text(encoding="utf-8")
                    st.download_button(
                        label="📚 Download as BibTeX",
                        data=bib_content.encode(),
                        file_name=f"{selected_collection}.bib",
                        mime="text/plain",
                        width="stretch",
                    )
                elif st.button("📚 Generate BibTeX", width="stretch"):
                    try:
                        result = subprocess.run(
                            [
                                "scilex-export-bibtex",
                                "--collect-name",
                                selected_collection,
                                "--output-dir",
                                str(output_dir),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if result.returncode == 0 and bib_file_path.exists():
                            st.success("✅ BibTeX generated — refresh to download.")
                            st.rerun()
                        else:
                            st.error("❌ Failed to generate BibTeX file")
                            if result.stderr:
                                st.error(f"Error: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        st.error("❌ BibTeX export timed out (>30s)")
                    except Exception as e:
                        st.error(f"❌ Error generating BibTeX: {e!s}")

            with col3:
                st.download_button(
                    label="📋 Download as JSON",
                    data=json_content.encode(),
                    file_name=f"{selected_collection}_filtered.json",
                    mime="application/json",
                    width="stretch",
                )

            # Zotero push option
            st.write("---")
            st.subheader("📤 Push to Zotero")

            zotero_col1, zotero_col2 = st.columns(2)

            with zotero_col1:
                zotero_collection_name = st.text_input(
                    "Zotero Collection Name",
                    value=selected_collection,
                    help=(
                        "Creates the collection in Zotero "
                        "if it doesn't exist.\n"
                        "If it already exists, "
                        "papers are added to it."
                    ),
                )

            with zotero_col2:
                if st.button("📚 Push to Zotero", width="stretch", type="primary"):
                    try:
                        st.info(
                            "⏳ Pushing papers to Zotero (this may take a moment)..."
                        )

                        result = subprocess.run(
                            [
                                "scilex-push-zotero",
                                "--collect-name",
                                zotero_collection_name,
                                "--output-dir",
                                str(output_dir),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )

                        if result.returncode == 0:
                            st.info(f"**Collection:** {zotero_collection_name}")
                            if result.stderr:
                                st.warning("Zotero push completed:")
                                st.caption(f"Output:\n{result.stderr[-500:]}")
                            else:
                                st.success("✅ Successfully pushed papers to Zotero!")
                        else:
                            st.error("❌ Failed to push papers to Zotero")
                            if result.stderr:
                                st.error(f"Error details:\n{result.stderr[-500:]}")

                    except subprocess.TimeoutExpired:
                        st.error("❌ Zotero push timed out (took >2 minutes)")
                    except Exception as e:
                        st.error(f"❌ Error pushing to Zotero: {e!s}")

        except Exception as e:
            st.error(f"Error loading results: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: COLLECTIONS HISTORY
# ═══════════════════════════════════════════════════════════════════════════

with tab4:
    st.header("📈 Collections History")

    output_path = Path(output_dir)
    collections_with_counts_t4 = get_available_collections(output_dir)

    if not collections_with_counts_t4:
        st.info("📭 No collections found.")
    else:
        # Build display table with file metadata
        collections_data = []
        for name, paper_count in collections_with_counts_t4.items():
            item_path = output_path / name
            csv_path = item_path / "aggregated_results.csv"
            try:
                if paper_count is not None and csv_path.exists():
                    row = {
                        "Collection": name,
                        "Status": "Completed",
                        "Papers": paper_count,
                        "Size (KB)": f"{csv_path.stat().st_size / 1024:.1f}",
                        "Created": pd.Timestamp(
                            item_path.stat().st_mtime, unit="s"
                        ).strftime("%Y-%m-%d %H:%M"),
                    }
                else:
                    row = {
                        "Collection": name,
                        "Status": "Partial",
                        "Papers": None,
                        "Size (KB)": None,
                        "Created": pd.Timestamp(
                            item_path.stat().st_mtime, unit="s"
                        ).strftime("%Y-%m-%d %H:%M"),
                    }
                collections_data.append(row)
            except OSError:
                continue

        if collections_data:
            # Sort by creation date descending
            collections_data.sort(key=lambda c: c["Created"], reverse=True)

            st.dataframe(
                pd.DataFrame(collections_data),
                width="stretch",
                hide_index=True,
            )

            # Delete collection
            st.write("---")
            st.subheader("🗑️ Delete a Collection")

            delete_names = [c["Collection"] for c in collections_data]
            delete_target = st.selectbox(
                "Select collection to delete",
                delete_names,
                key="delete_collection_target",
                format_func=lambda x: f"📦 {x}",
            )

            confirm_delete = st.checkbox(
                f"I confirm I want to permanently delete **{delete_target}**",
                key="confirm_delete",
            )

            if st.button(
                "🗑️ Delete Collection",
                disabled=not confirm_delete,
                type="secondary",
            ):
                try:
                    resp = requests.delete(
                        f"{api_base_url.rstrip('/')}/collections/{delete_target}",
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        st.success(f"✅ Collection '{delete_target}' deleted.")
                        st.rerun()
                    else:
                        detail = resp.json().get("detail", resp.text)
                        st.error(f"❌ Delete failed: {detail}")
                except requests.RequestException as exc:
                    st.error(f"❌ Could not reach backend: {exc}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 5: HELP
# ═══════════════════════════════════════════════════════════════════════════

with tab5:
    st.header("ℹ️ Help & Documentation")

    st.markdown(
        """
    ## Overview

    **SciLEx** helps you systematically collect academic papers from multiple sources and analyze them.

    ### Key Features

    - **Multi-Source Collection**: Search 10+ academic databases simultaneously
    - **Advanced Filtering**: Filter by year, source, publication type, and more
    - **Quality Ranking**: Automatically rank papers by relevance to your keywords
    - **Multiple Exports**: Export results as CSV, BibTeX, or JSON
    - **Citation Tracking**: Include citation counts from CrossRef

    ### Workflow

    1. **Configure API Keys** (sidebar)
       - Add API credentials for paid services (IEEE, Elsevier, Springer, etc.)
       - Free APIs don't require keys

    2. **New Collection** (Tab 1)
       - Enter your research keywords
       - Select years and data sources
       - Configure quality filters
       - Click "Start Collection Pipeline"

    3. **View Results** (Tab 2)
       - Select a completed collection
       - View statistics and paper list
       - Browse papers with pagination

    4. **Filter & Export** (Tab 3)
       - Apply additional filters
       - Download results in different formats
       - Share findings with collaborators

    ### Available Data Sources

    **Free APIs:**
    - **SemanticScholar** - Comprehensive academic database
    - **OpenAlex** - Open, machine-readable database
    - **Arxiv** - Preprints in physics, CS, math, etc.
    - **PubMed** - Biomedical and life sciences literature
    - **DBLP** - Computer science bibliography
    - **HAL** - French multidisciplinary archive

    **Paid APIs** (require subscription):
    - **IEEE Xplore** - IEEE journals and conferences
    - **Elsevier/ScienceDirect** - Major journal publisher
    - **Springer** - Springer journals and books

    **Integration:**
    - **Zotero** - Push results to Zotero library
    - **HuggingFace** - Enrich results with ML models/datasets

    ### Keywords

    Enter keywords as separate lines. You can use two keyword groups:

    - **Primary Group**: Papers must match at least one keyword
    - **Secondary Group** (optional): If provided, papers must match keywords from BOTH groups

    Example:
    ```
    Group 1: "LLM", "Large Language Model", "GPT"
    Group 2: "hallucination", "fact verification", "grounding"
    ```

    Only papers mentioning LLM/GPT AND hallucination/fact verification are collected.

    ### Quality Filters

    - **Abstract Length**: Remove very short/long abstracts (likely incomplete)
    - **Publication Type**: Filter by peer-reviewed articles, conference papers, etc.
    - **Relevance Scoring**: Rank by match to your keywords
    - **Max Papers**: Return top N papers by relevance score

    ### Tips & Tricks

    - Start with broad keywords and refine based on results
    - Use 2-3 keyword groups for highly specific searches
    - Filter by publication type to ensure quality
    - Combine multiple free APIs for comprehensive coverage
    - Use citation counts to identify influential papers

    ### Troubleshooting

    **No results found?**
    - Check your keywords (try simpler terms)
    - Expand the year range
    - Add more data sources

    **Collection is slow?**
    - Use fewer APIs
    - Reduce year range
    - Try bulk mode for SemanticScholar (if approved)

    **Missing API results?**
    - Verify API keys are configured correctly
    - Check rate limits for your API tier
    - Some APIs may block certain queries

    ### Next Steps

    - See [docs/user-guides/python-scripting.md](https://scilex.readthedocs.io/en/latest/user-guides/python-scripting.html) for programmatic usage
    - Check [docs/getting-started/configuration.md](https://scilex.readthedocs.io/en/latest/getting-started/configuration.html) for detailed config options
    - Review [docs/user-guides/advanced-filtering.md](https://scilex.readthedocs.io/en/latest/user-guides/advanced-filtering.html) for advanced techniques
    """
    )
