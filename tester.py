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

    # Parse args from sys.argv
    parsed = parser.parse_args()

    # Sleep if requested
    if parsed.sleep is not None:
        time.sleep(parsed.sleep)

    # Print the entire command line exactly as received
    print("Command line:", " ".join(sys.argv))

    # For each env key, print the key=value (using None if missing)
    for key in parsed.env:
        value = os.environ.get(key, None)
        print(f"{key}={value}")

if __name__ == "__main__":
    main()
