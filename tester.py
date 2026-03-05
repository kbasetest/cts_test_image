#!/usr/bin/env python3

import argparse
from pathlib import Path
import grp
import os
import pwd
import stat
import sys
import time


def print_entry(path: Path) -> None:
    st = path.stat()
    mode = stat.filemode(st.st_mode)
    try:
        user = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        user = f"[{st.st_uid}]"
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = f"[{st.st_gid}]"
    print(f"{mode} {user} {group} {path.absolute()}")


def print_all_files(path: Path) -> None:
    print_entry(path)
    if path.is_dir():
        for item in path.iterdir():
            print_all_files(item)


def touch(path_str: str) -> None:
    p = Path(path_str)
    if path_str.endswith("/"):
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()


def main():
    parser = argparse.ArgumentParser(
        description="Simulate and inspect container behavior for testing purposes"
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
    
    parser.add_argument(
        "-l", "--list",
        metavar="DIRECTORY OR FILE",
        help="list the directory or file."
    )
    
    parser.add_argument(
        "-t", "--touch",
        action="append",
        default=[],
        metavar="PATH",
        help="Create directories in PATH; touch the final entry if PATH has no trailing slash (repeatable)"
    )

    parser.add_argument(
        "-x", "--exitcode",
        type=int,
        metavar="EXITCODE",
        help="exit the program with the given code after doing everything else."
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
        
    for path_str in parsed.touch:
        touch(path_str)

    if parsed.list:
        p = Path(parsed.list).absolute().resolve()
        print(f"\nListing {p}")
        print_all_files(Path(p))
        print()

    if parsed.sleep is not None:
        time.sleep(parsed.sleep)
    
    if parsed.exitcode:
        sys.exit(parsed.exitcode)


if __name__ == "__main__":
    main()
