"""Robust reading of result CSVs and graph warnings."""

import importlib.util

from scilex.gui.services import analyses as service


def test_read_result_csv_guesses_delimiter(tmp_path):
    comma = tmp_path / "a.csv"
    comma.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    semicolon = tmp_path / "b.csv"
    semicolon.write_text("a;b;c\n1;2;3\n", encoding="utf-8")
    assert list(service.read_result_csv(comma).columns) == ["a", "b", "c"]
    assert list(service.read_result_csv(semicolon).columns) == ["a", "b", "c"]


def test_read_result_csv_skips_malformed_lines(tmp_path):
    path = tmp_path / "clusters_cocitation.csv"
    path.write_text(
        "cluster_id,title,pagerank\n1,A,0.1\n1,B,0.2\n2,x,y,z,1,2,3,4,5,6\n2,C,0.3\n",
        encoding="utf-8",
    )
    frame = service.read_result_csv(path)
    assert list(frame["title"]) == ["A", "B", "C"]


def test_read_result_csv_unreadable_raises_value_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    try:
        service.read_result_csv(path)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_warnings_texts():
    assert "Citations tab" in service.NO_EDGES_WARNING
    assert "PageRank" in service.NO_SCIPY_WARNING
    assert importlib.util.find_spec("pandas") is not None


def test_summaries_warn_instead_of_listing_one_paper_communities(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    config = ctx.workspace.load_config(review)
    graph_dir = review.collection_dir / service.GRAPH_DIRNAME
    graph_dir.mkdir(parents=True)
    (graph_dir / "clusters_cocitation.csv").write_text(
        "cluster_id,title\n0,A\n1,B\n2,C\n", encoding="utf-8"
    )
    result = service.run_summaries(config, lambda percent, message: None)
    assert "No co-citation links found" in result.message
    assert result.files == []
