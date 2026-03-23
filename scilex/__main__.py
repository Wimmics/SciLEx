"""Entry point for `python -m scilex`."""

import sys


COMMANDS = {
    "collect": "scilex.run_collection",
    "aggregate": "scilex.aggregate_collect",
    "enrich": "scilex.enrich_with_hf",
    "export-bibtex": "scilex.export_to_bibtex",
    "push-zotero": "scilex.push_to_zotero",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python -m scilex <command> [options]")
        print()
        print("Commands:")
        print("  collect        Collect papers from academic APIs")
        print("  aggregate      Deduplicate, filter, and rank papers")
        print("  enrich         Enrich papers with HuggingFace metadata")
        print("  export-bibtex  Export aggregated papers to BibTeX")
        print("  push-zotero    Push aggregated papers to Zotero")
        sys.exit(0)

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    # Remove the subcommand from argv so the module sees its own args
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    from importlib import import_module

    module = import_module(COMMANDS[command])
    module.main()


if __name__ == "__main__":
    main()
