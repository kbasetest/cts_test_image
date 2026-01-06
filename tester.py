#!/usr/bin/env python3

import argparse
import os
import sys
import time

def main():
    parser = argparse.ArgumentParser(
        description="Print command line and selected environment variables"
    )

    # Arbitrary positional arguments
    parser.add_argument("args", nargs="*", help="Positional arguments")

    # Arbitrary number of -e / --env flags
    parser.add_argument(
        "-e", "--env",
        action="append",
        default=[],
        metavar="KEY",
        help="Environment variable key to print"
    )

    # Float sleep flag
    parser.add_argument(
        "-s", "--sleep",
        type=float,
        metavar="SECONDS",
        help="Sleep for the given number of seconds (float allowed)"
    )
    parser.add_argument(
        "-o", "--out",
        metavar="OUT_TEXT",
        help="Print the given text to stdout"
    )
    parser.add_argument(
        "-r", "--error",
        metavar="ERROR_TEXT",
        help="Print the given text to stderr"
    )

    parsed = parser.parse_args()

    print("Command line:", " ".join(sys.argv))

    for key in parsed.env:
        value = os.environ.get(key, None)
        print(f"{key}={value}")
        
    if parsed.out:
        print(parsed.out)
        
    if parsed.error:
        print(parsed.error, file=sys.stderr)

    if parsed.sleep is not None:
        time.sleep(parsed.sleep)


if __name__ == "__main__":
    main()
