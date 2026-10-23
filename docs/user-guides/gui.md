# Desktop application

The SciLEx desktop application runs a literature review without the command line.
It works on the same files as the CLI: a review is a folder containing a `scilex.yml`,
and API keys live in `~/.config/scilex/keys.yml`. You can switch between the app and
the `scilex-*` commands at any time.

> Status: early version (foundation). Available: create or open a review, run the
> collection and aggregation with progress and cancellation. Coming next: configuration
> and API key editors, paper screening, export, analyses. Until then, edit `scilex.yml`
> and `keys.yml` with a text editor.

## Install

Download the archive for your system from the project's GitHub Actions artifacts
(workflow "GUI build"), then:

- **macOS** (`SciLEx-macos.dmg`): open the image and drag `SciLEx.app` to Applications.
  The app is not signed yet: the first time, right-click the app, choose **Open**, then
  **Open** again in the warning dialog. Later launches work normally.
- **Windows** (`SciLEx-windows.zip`): extract the folder and run `SciLEx.exe`.
  SmartScreen may warn about an unknown publisher: click **More info**, then **Run anyway**.
- **Linux** (`SciLEx-linux.tar.gz`): extract it and run `SciLEx/SciLEx`.

From a development checkout instead:

```bash
uv sync --extra gui
uv run scilex-gui            # native window
uv run scilex-gui --browser  # same UI in a browser tab (useful for debugging)
```

## First steps

1. **New review**: choose a folder (created if needed), a name and optionally a
   template (machine learning, bioinformatics…). The app writes `scilex.yml` there.
   Or **Open a folder** that already contains a `scilex.yml`.
2. Edit `scilex.yml` in that folder (keywords, years, APIs). See
   [the configuration reference](../reference/configuration.md).
3. In the review, open **② Collect** and click **Run**. Progress and logs are shown;
   **Cancel** stops the collection at the next query.
4. Results are written to `<folder>/output/<name>/aggregated_results.csv`, exactly as
   with `scilex-collect` followed by `scilex-aggregate`.

Only one collection runs at a time in the app.

## Troubleshooting

- Check an installation without opening a window: run the executable with `--self-test`
  (for example `SciLEx.app/Contents/MacOS/SciLEx --self-test` on macOS).
- Logs are written to `scilex-gui.log` in your user log folder
  (`~/Library/Logs/scilex` on macOS, `%LOCALAPPDATA%\scilex\Logs` on Windows,
  `~/.local/state/scilex/log` on Linux).
- Unexpected errors show a dialog with **Copy diagnostics**: paste it into a GitHub issue.
