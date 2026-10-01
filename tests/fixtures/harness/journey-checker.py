"""The checker this journey names. It is READ by the harness and never run.

`read_the_success_check` opens this file, looks for the shapes a checker
takes, and reports whether it is a program. That it would actually work is
beside the point of the gate it opens - G0 separates 'there is a definition
of success' from 'there is not', and whether the checker is CORRECT is what
the twenty tasks are for.
"""


def is_right(answer: str, expected: str) -> bool:
    return answer.strip().casefold() == expected.strip().casefold()
