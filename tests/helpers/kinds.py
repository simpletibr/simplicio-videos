"""The closed list of background-task kinds, as it is today: the one golden every test that counts the kinds compares `jobs.KINDS` with.

A literal on purpose, never derived from the code: the point is to freeze the list and its order, so adding, renaming or reordering a
kind (a change of `simplicio.job/v1`, and of the text of `jobs submit --help`) is something the tests make the author see and decide.
"""

KINDS_DE_HOJE = ["swap-run", "voice", "rea-video", "moneyprinter", "montage-tool", "video-to-skill"]
