#!/usr/bin/env python3

import argparse
import os
import sys

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

    # Parse args from sys.argv
    parsed = parser.parse_args()

    # Print the entire command line exactly as received
    print("Command line:", " ".join(sys.argv))

    # For each env key, print the key=value (using None if missing)
    for key in parsed.env:
        value = os.environ.get(key, None)
        print(f"{key}={value}")

if __name__ == "__main__":
    main()
