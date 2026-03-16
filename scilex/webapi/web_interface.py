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

# Add src/ to path for SciLEx imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
API_CONFIG_PATH = PROJECT_ROOT / "scilex" / "api.config.yml"


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

    # API Keys — flat list with status colors
    st.subheader("🔑 API Keys")
    saved_api_config = load_local_api_config()

    api_options = {
        "SemanticScholar": {"api_key": "API Key"},
        "IEEE": {"api_key": "API Key"},
        "Elsevier": {
            "api_key": "API Key",
            "inst_token": "Institutional Token",
        },
        "Springer": {"api_key": "API Key"},
        "Zotero": {
            "api_key": "API Key",
            "user_id": "User ID",
            "user_mode": "User Mode (user/group)",
        },
        "HuggingFace": {"token": "Access Token"},
    }

    for api_name, fields in api_options.items():
        api_saved = saved_api_config.get(api_name, {})
        configured = [f for f in fields if api_saved.get(f)]
        is_configured = bool(configured)

        # Green when configured, grey when not
        if is_configured:
            st.markdown(
                f"<span style='color: #28a745; font-weight: 600;'>● {api_name}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<span style='color: #999; font-weight: 400;'>○ {api_name}</span>",
                unsafe_allow_html=True,
            )

        current_input_values = {}
        for field_name, field_label in fields.items():
            default_value = str(api_saved.get(field_name, "") or "")
            if api_name == "Zotero" and field_name == "user_mode" and not default_value:
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
                            error_detail = response.json().get("detail", response.text)
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

    # Output directory
    output_dir = st.text_input(
        "Output Directory",
        value=DEFAULT_OUTPUT_DIR,
        help="Where to save collected papers and results",
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

    with st.form("collection_form"):
        st.subheader("1️⃣ Search Parameters")

        col1, col2 = st.columns(2)

        with col1:
            collect_name = st.text_input(
                "Collection Name",
                value="my_research_",
                help="Unique identifier for this collection",
            )
            years = st.multiselect(
                "Publication Years",
                options=list(range(2026, 2000, -1)),
                default=[2025, 2026],
                help="Select years to search",
            )

        with col2:
            semantic_scholar_mode = st.selectbox(
                "Semantic Scholar Mode",
                ["regular", "bulk"],
                help=(
                    "regular: Standard search (100 papers/request)\n"
                    "bulk: Fast mode for large collections (1000 papers/request, requires approval)"
                ),
            )
            aggregate_citations = st.checkbox(
                "Fetch Citation Counts",
                value=True,
                help="Include citation count from CrossRef/OpenCitations",
            )
            enable_enrichment = st.checkbox(
                "Enable HuggingFace Enrichment",
                value=False,
                help="Enrich papers with HuggingFace tags, URLs, and GitHub repos",
            )

        st.subheader("2️⃣ Keywords")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Primary Keywords Group**")
            keywords_group1 = st.text_area(
                "Primary keywords (one per line)",
                value="RAG\nRetrieval Augmented Generation\nLLM\nLarge Language Model",
                help="Papers must contain at least one of these keywords",
                key="keywords1",
            )

        with col2:
            st.write("**Secondary Keywords Group (Optional)**")
            keywords_group2 = st.text_area(
                "Secondary keywords (one per line, or leave empty)",
                value="Knowledge Graph\nknowledge graphs\nsemantic network",
                help="If provided, papers must match keywords from BOTH groups",
                key="keywords2",
            )

        bonus_keywords_text = st.text_area(
            "Bonus Keywords (Optional)",
            value="",
            help="Optional keywords that boost relevance without filtering papers",
            key="bonus_keywords",
        )

        st.subheader("3️⃣ Data Sources")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Free APIs**")
            free_apis = st.multiselect(
                "Free sources",
                options=[
                    "SemanticScholar",
                    "OpenAlex",
                    "Arxiv",
                    "PubMed",
                    "PubMedCentral",
                    "DBLP",
                    "HAL",
                    "Istex",
                ],
                default=["SemanticScholar", "OpenAlex", "Arxiv"],
                label_visibility="collapsed",
                key="free_apis",
            )

        with col2:
            st.write("**Paid APIs** (requires key)")
            paid_apis = st.multiselect(
                "Paid sources",
                options=["IEEE", "Elsevier", "Springer"],
                default=[],
                label_visibility="collapsed",
                key="paid_apis",
            )

        selected_apis = free_apis + paid_apis

        st.subheader("4️⃣ Quality Filters")

        col1, col2 = st.columns(2)

        with col1:
            min_abstract = 50
            max_abstract = 1000
            enable_base_filters = st.checkbox(
                "Enable Base Filters",
                value=True,
            )

            if enable_base_filters:
                min_abstract = st.slider(
                    "Minimum Abstract Length (words)",
                    min_value=0,
                    max_value=500,
                    value=50,
                )
                max_abstract = st.slider(
                    "Maximum Abstract Length (words)",
                    min_value=100,
                    max_value=2000,
                    value=1000,
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
                default=["journalArticle", "conferencePaper"],
                label_visibility="collapsed",
            )

        col1, col2 = st.columns(2)

        with col1:
            apply_relevance = st.checkbox(
                "Sort by Relevance Score",
                value=True,
                help="Rank papers by relevance to your keywords",
            )

        with col2:
            max_papers = st.number_input(
                "Maximum Papers to Keep",
                min_value=10,
                max_value=10000,
                value=500,
                step=50,
                help="Return top N papers by relevance",
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
            "🚀 Start Collection Pipeline",
            width="stretch",
            type="primary",
        )

        if submitted:
            # Validation
            if not keywords_list[0]:
                st.error("❌ Please enter at least one primary keyword")
            elif not selected_apis:
                st.error("❌ Please select at least one data source")
            elif not years:
                st.error("❌ Please select at least one year")
            else:
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
            data = resp.json()

            # Show progress bar
            progress_value = max(0, min(data.get("progress", 0), 100))
            st.progress(progress_value / 100, text=data.get("message", ""))

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

            # Terminal states
            if data["status"] in ("completed", "failed", "cancelled"):
                if data["status"] == "completed":
                    st.success("Pipeline completed successfully!")
                    if data.get("stats"):
                        st.json(data["stats"])
                elif data["status"] == "cancelled":
                    st.warning("Pipeline was cancelled.")
                elif data["status"] == "failed":
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

    # Check for existing collections
    output_path = Path(output_dir)
    collections = []

    if output_path.exists():
        for item in output_path.iterdir():
            if item.is_dir() and item.name not in ["text_to_sparql", "text2sparql"]:
                csv_path = item / "aggregated_results.csv"
                if csv_path.exists():
                    collections.append(item.name)

    if not collections:
        st.info(
            "📭 No collections found. Start a new collection in the **New Collection** tab."
        )
    else:
        selected_collection = st.selectbox(
            "Select a Collection",
            collections,
            format_func=lambda x: f"📦 {x}",
        )

        csv_path = output_path / selected_collection / "aggregated_results.csv"

        try:
            df = pd.read_csv(csv_path, delimiter=";")

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
                    source_counts = df["archive"].value_counts()
                    st.bar_chart(source_counts)

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

            # Select columns to display
            display_columns = [
                col
                for col in [
                    "title",
                    "authors",
                    "year",
                    "archive",
                    "nb_citation",
                    "abstract",
                ]
                if col in df.columns
            ]

            st.dataframe(
                display_df[display_columns],
                width="stretch",
                height=400,
            )

        except Exception as e:
            st.error(f"Error loading results: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: FILTER & EXPORT
# ═══════════════════════════════════════════════════════════════════════════

with tab3:
    st.header("Filter & Export Results")

    # Check for existing collections
    output_path = Path(output_dir)
    collections = []

    if output_path.exists():
        for item in output_path.iterdir():
            if item.is_dir() and item.name not in ["text_to_sparql", "text2sparql"]:
                csv_path = item / "aggregated_results.csv"
                if csv_path.exists():
                    collections.append(item.name)

    if not collections:
        st.info("📭 No collections found.")
    else:
        selected_collection = st.selectbox(
            "Select a Collection",
            collections,
            key="export_collection",
            format_func=lambda x: f"📦 {x}",
        )

        csv_path = output_path / selected_collection / "aggregated_results.csv"

        try:
            df = pd.read_csv(csv_path, delimiter=";")

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

                    # Source filter
                    if "archive" in df.columns:
                        sources = st.multiselect(
                            "Sources",
                            options=df["archive"].unique(),
                            default=list(df["archive"].unique()),
                        )
                        if sources:
                            df = df[df["archive"].isin(sources)]

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

            if True:  # apply_filters can be used as trigger if needed
                st.success(f"✅ Filtered to {len(df)} papers")

                # Export options
                st.subheader("📥 Export Options")

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("📊 Download as CSV", width="stretch"):
                        csv_content = df.to_csv(index=False, sep=";")
                        st.download_button(
                            label="Download CSV",
                            data=csv_content.encode(),
                            file_name=f"{selected_collection}_filtered.csv",
                            mime="text/csv",
                            width="stretch",
                        )

                with col2:
                    if st.button("📚 Download as BibTeX", width="stretch"):
                        try:
                            # Prepare BibTeX export output
                            bib_output_dir = output_path / selected_collection
                            bib_file_path = bib_output_dir / "aggregated_results.bib"

                            # Run BibTeX export command with CLI arguments
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
                                # Read BibTeX content
                                with bib_file_path.open("r", encoding="utf-8") as f:
                                    bib_content = f.read()

                                st.download_button(
                                    label="⬇️ Download BibTeX File",
                                    data=bib_content.encode(),
                                    file_name=f"{selected_collection}.bib",
                                    mime="text/plain",
                                    width="stretch",
                                )
                                st.success(
                                    f"✅ BibTeX file generated ({len(bib_content)} bytes)"
                                )
                            else:
                                st.error("❌ Failed to generate BibTeX file")
                                if result.stderr:
                                    st.error(f"Error: {result.stderr}")

                        except subprocess.TimeoutExpired:
                            st.error("❌ BibTeX export timed out (took >30 seconds)")
                        except Exception as e:
                            st.error(f"❌ Error generating BibTeX: {str(e)}")

                with col3:
                    if st.button("📋 Download as JSON", width="stretch"):
                        json_content = df.to_json(orient="records", indent=2)
                        st.download_button(
                            label="Download JSON",
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
                        help="Name of the Zotero collection to push papers to",
                    )

                with zotero_col2:
                    if st.button("📚 Push to Zotero", width="stretch", type="primary"):
                        try:
                            st.info(
                                "⏳ Pushing papers to Zotero (this may take a moment)..."
                            )

                            # Run push to Zotero command
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
                                # Display the command output which contains summary stats
                                if result.stderr:
                                    # Log output is in stderr for the logging handler
                                    st.warning("Zotero push completed:")
                                    stderr_tail = (
                                        result.stderr[-500:]
                                        if len(result.stderr) > 500
                                        else result.stderr
                                    )
                                    st.caption(f"Output:\n{stderr_tail}")
                                else:
                                    st.success(
                                        "✅ Successfully pushed papers to Zotero!"
                                    )
                            else:
                                st.error("❌ Failed to push papers to Zotero")
                                if result.stderr:
                                    # Show last 500 chars of error
                                    error_msg = (
                                        result.stderr[-500:]
                                        if len(result.stderr) > 500
                                        else result.stderr
                                    )
                                    st.error(f"Error details:\n{error_msg}")

                        except subprocess.TimeoutExpired:
                            st.error("❌ Zotero push timed out (took >2 minutes)")
                        except Exception as e:
                            st.error(f"❌ Error pushing to Zotero: {str(e)}")

                # HuggingFace Enrichment
                st.write("---")
                st.subheader("🤗 Enrich with HuggingFace")

                if st.button("🤗 Enrich Papers", width="stretch", type="primary"):
                    try:
                        st.info(
                            "⏳ Running HuggingFace enrichment (this may take a while)..."
                        )

                        result = subprocess.run(
                            ["scilex-enrich"],
                            capture_output=True,
                            text=True,
                            timeout=300,
                        )

                        if result.returncode == 0:
                            st.success("✅ HuggingFace enrichment completed!")
                            if result.stderr:
                                stderr_tail = (
                                    result.stderr[-500:]
                                    if len(result.stderr) > 500
                                    else result.stderr
                                )
                                st.caption(f"Output:\n{stderr_tail}")
                        else:
                            st.error("❌ Enrichment failed")
                            if result.stderr:
                                error_msg = (
                                    result.stderr[-500:]
                                    if len(result.stderr) > 500
                                    else result.stderr
                                )
                                st.error(f"Error: {error_msg}")

                    except subprocess.TimeoutExpired:
                        st.error("❌ Enrichment timed out (took >5 minutes)")
                    except Exception as e:
                        st.error(f"❌ Error running enrichment: {str(e)}")

        except Exception as e:
            st.error(f"Error loading results: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: COLLECTIONS HISTORY
# ═══════════════════════════════════════════════════════════════════════════

with tab4:
    st.header("📈 Collections History")

    output_path = Path(output_dir)

    if not output_path.exists():
        st.info("📭 No collections yet.")
    else:
        collections_data = []

        for item in sorted(
            output_path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            if item.is_dir() and item.name not in ["text_to_sparql", "text2sparql"]:
                csv_path = item / "aggregated_results.csv"
                if csv_path.exists():
                    try:
                        df = pd.read_csv(csv_path, delimiter=";", nrows=1)
                        size = csv_path.stat().st_size
                        mtime = item.stat().st_mtime

                        collections_data.append(
                            {
                                "Collection": item.name,
                                "Papers": len(pd.read_csv(csv_path, delimiter=";")),
                                "Size (KB)": f"{size / 1024:.1f}",
                                "Created": pd.Timestamp(mtime, unit="s").strftime(
                                    "%Y-%m-%d %H:%M"
                                ),
                            }
                        )
                    except Exception:
                        pass

        if collections_data:
            st.dataframe(
                pd.DataFrame(collections_data),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("📭 No collections found.")

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
