"""Module runner for the Proxbox CLI."""

import os

from proxbox_cli import main
from proxbox_cli.docgen.engine import configure_docgen_console

if os.environ.get("_PROXBOX_CLI_DOCGEN") == "1":
    configure_docgen_console()


if __name__ == "__main__":
    raise SystemExit(main())
