"""Run an entry point in process and capture what it printed."""

import sys


def run_main(main, argv, capsys, *, text_exit: bool = False):
    """`(rc, stdout, stderr)` of `main(argv)`. A SystemExit becomes its code (argparse exits for --help and usage errors).

    With `text_exit`, `SystemExit("texto")` is the engine's text error: the text goes to stderr and rc is 1."""
    try:
        rc = main(argv)
    except SystemExit as e:
        if text_exit and isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            rc = 1
        else:
            rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err
