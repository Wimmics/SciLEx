# Desktop application

The SciLEx desktop application runs a literature review without the command line.
It works on the same files as the CLI: a review is a folder containing a `scilex.yml`,
and API keys live in `~/.config/scilex/keys.yml`. You can switch between the app and
the `scilex-*` commands at any time.

Screens of a review: ① Configure, ② Collect, ③ Screen, ④ Export, ⑤ Analyses, plus
API keys. Screen, Export and Analyses unlock once a collection has been aggregated.

## Install

Download the archive for your system from the
[latest release](https://github.com/Wimmics/SciLEx/releases/latest), then:

- **macOS** (`SciLEx-macos.dmg`): open the image and drag `SciLEx.app` to Applications.
  The app is not signed yet: the first time, right-click the app, choose **Open**, then
  **Open** again in the warning dialog. Later launches work normally.
- **Windows** (`SciLEx-windows.zip`): extract the folder and run `SciLEx.exe`.
  SmartScreen may warn about an unknown publisher: click **More info**, then **Run anyway**.
- **Linux** (`SciLEx-linux.tar.gz`, needs glibc 2.34+, e.g. Ubuntu 22.04 or later): extract
  it and run `SciLEx/SciLEx` (double-click it in the file manager, or run it from a terminal).
  If the window cannot open (no display, missing system library), the app says why in the
  terminal and opens in your web browser instead; every feature works there too.

Maintainers publish a release by pushing a `gui-v*` tag (for example
`git tag gui-v0.1.0 && git push origin gui-v0.1.0`): the "GUI build" workflow builds the
three archives, self-tests them and attaches them to the GitHub Release of that tag.

From a development checkout instead:

```bash
uv sync --extra gui
uv run scilex-gui            # native window
uv run scilex-gui --browser  # same UI in a browser tab (useful for debugging)
```

## First steps

1. **New review**: give a name, optionally a folder and a template. Without a folder,
   the review goes to `~/SciLEx/<name>`; a relative folder such as `Test` also starts
   in `~/SciLEx` (an absolute path is used as is). The app writes
   `scilex.yml` there. Or **Open a folder** that already contains a `scilex.yml`.
2. **API keys** (once for all reviews), then **① Configure**, **② Collect**,
   **③ Screen**, **④ Export**, and optionally **⑤ Analyses**.

Only one job (collection, export, analysis) runs at a time in the app.

## ① Configure

Edits the review's `scilex.yml` without a text editor. The **Search** section holds the
name, the keyword groups (a paper must contain at least one term of *each* group), the
years, the sources and the maximum number of papers per query. Other sections (filters,
citations, ranking…) fold out, with help on hover and a badge showing where each value
comes from (file or preset). Errors are shown live and block saving. Only values that
differ from the defaults are written, and comments in the file are lost when saving from
the form. **Edit scilex.yml directly** opens the raw file (comments kept); use it to
repair a file the form cannot load.

## API keys

Keys are global: shared by all reviews and stored in one file whose path is shown
(`$SCILEX_KEYS`, else `~/.config/scilex/keys.yml`, readable by you only). Type each key
(the eye icon shows it), add several for rotation if needed, click **Test** to check it,
then **Save**. Zotero, the Unpaywall and CrossRef e-mails and the rate limits
(**Advanced**) are set here too. An environment variable `SCILEX_<API>_<FIELD>` takes
precedence over the file; a warning says so.

## ② Collect

Check the summary line (APIs, years, keyword groups), then click **Run**. A table shows
each API's progress, papers, errors and state; the aggregation steps follow. **Only
papers since** (YYYY-MM-DD) collects recent papers only. If a collection was
interrupted, **Resume interrupted collection** continues where it stopped. At the end, a
summary (collected, after deduplication, kept) and the PRISMA and aggregation reports are
available. **Cancel** stops the collection at the next query; the aggregation cannot be
interrupted. Results go to `<folder>/output/<name>/aggregated_results.csv`, exactly as
with `scilex-collect` then `scilex-aggregate`.

## ③ Screen

Lists the aggregated papers by relevance score. Select a paper to read its abstract and
open its DOI, then click **Include**, **Exclude** or **Maybe**, or press **I**, **E**,
**M**; the arrows (or **J**/**K**) move between papers. A note can go with each decision.
Decisions are saved at once to `output/<name>/screening.csv` and survive a new
aggregation; decisions on papers that disappeared are listed as *orphans* and can be
forgotten. A note typed without a decision is not kept.

## ④ Export

Choose the papers: only those marked *included* while screening, or all of them. Four
formats: BibTeX, CSV (`;`-separated, with the screening decision and note), RDF/Turtle,
and Zotero (a collection named after the review; duplicates skipped). Each export is
written to the review's `exports/` folder, with the scope and a timestamp in its name;
the path is shown at the end with a button to reveal it, and previous exports are listed.
The Zotero button stays disabled until the Zotero key and library id are set in
**API keys**.

## ⑤ Analyses

Tabs: charts, keyword suggestions, Papers with Code enrichment, citations, snowball, citation
graph and community summaries. Each tab describes the analysis, offers its main options
and a **Run** button; progress and logs are shown live. Results (images, Markdown
reports, tables) are read from the collection folder and shown again when the tab opens.
Snowball and the graph need the citation data: run the **Citations** tab first (it
fetches the references and citing papers of the corpus). Snowball adds the new papers to
`aggregated_results.csv` itself (column `snowball_depth`), so Zotero and the exports
include them; the original file is kept once as `aggregated_results_pre_snowball.csv`.
Untick **Add to the collection** to write `aggregated_results_snowball.csv` instead and
leave the collection unchanged (`scilex-snowball --separate-file` on the command line).
Re-running the aggregation replaces the file and drops them. Keyword suggestions and
summaries need the graph to have run first. **Cancel** stops an analysis at the end of
its current step; citations already fetched are kept. **Run** buttons are disabled while
another job is running.

## Troubleshooting

- Check an installation without opening a window: run the executable with `--self-test`
  (for example `SciLEx.app/Contents/MacOS/SciLEx --self-test` on macOS).
- Logs are written to `scilex-gui.log` in your user log folder
  (`~/Library/Logs/scilex` on macOS, `%LOCALAPPDATA%\scilex\Logs` on Windows,
  `~/.local/state/scilex/log` on Linux).
- Unexpected errors show a dialog with **Copy diagnostics**: paste it into a GitHub issue.
