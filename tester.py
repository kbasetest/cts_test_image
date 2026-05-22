#!/usr/bin/env python3

import argparse
from pathlib import Path
import grp
import os
import pwd
import random
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
        "-R", "--random",
        metavar="SLEEP,CODE,W_RUN,W_FAIL",
        help="randomly run (sleep SLEEP secs), complete (exit 0), or fail (exit CODE); "
             "W_RUN and W_FAIL are weights (0.0-1.0), W_COMPLETE = 1 - W_RUN - W_FAIL"
    )

    parser.add_argument(
        "-x", "--exitcode",
        type=int,
        metavar="EXITCODE",
        help="exit the program with the given code after doing everything else."
    )

    parser.add_argument(
        "-p", "--proc-num",
        type=int,
        metavar="N",
        help="0-based process number; indexes into --proc-exitcodes / --proc-sleeps"
    )
    parser.add_argument(
        "--proc-exitcodes",
        metavar="CODES",
        help="comma-separated exit codes indexed by --proc-num (e.g. '0,0,1,1')"
    )
    parser.add_argument(
        "--proc-sleeps",
        metavar="SLEEPS",
        help="comma-separated sleep durations indexed by --proc-num (e.g. '300,300,0,0')"
    )

    parsed = parser.parse_args()

    uid = os.getuid()
    try:
        uname = pwd.getpwuid(uid).pw_name
    except KeyError:
        uname = None
    print(f"Running as: {uname} [{uid}]" if uname else f"Running as: [{uid}]")

    print("Command line:", " ".join(sys.argv))

    if parsed.random:
        parts = parsed.random.split(",")
        if len(parts) != 4:
            print("--random requires format SLEEP,CODE,W_RUN,W_FAIL", file=sys.stderr)
            sys.exit(1)
        sleep_secs, fail_code, w_run, w_fail = float(parts[0]), int(parts[1]), float(parts[2]), float(parts[3])
        errors = []
        if sleep_secs < 0:
            errors.append(f"SLEEP must be >= 0, got {sleep_secs}")
        if not (0 < fail_code <= 255):
            errors.append(f"CODE must be 1-255, got {fail_code}")
        if not (0.0 <= w_run <= 1.0):
            errors.append(f"W_RUN must be 0.0-1.0, got {w_run}")
        if not (0.0 <= w_fail <= 1.0):
            errors.append(f"W_FAIL must be 0.0-1.0, got {w_fail}")
        w_complete = 1.0 - w_run - w_fail
        if w_complete < 0:
            errors.append(f"W_RUN + W_FAIL must be <= 1.0, got {w_run} + {w_fail}")
        if errors:
            for e in errors:
                print(f"--random: {e}", file=sys.stderr)
            sys.exit(1)
        roll = random.random()
        if roll < w_run:
            print("Random behavior: running")
            parsed.sleep = sleep_secs
        elif roll < w_run + w_fail:
            print("Random behavior: fail")
            parsed.exitcode = fail_code
        else:
            print("Random behavior: complete")

    if parsed.proc_num is not None:
        if not parsed.proc_exitcodes and not parsed.proc_sleeps:
            print("--proc-num requires at least one of --proc-exitcodes or --proc-sleeps", file=sys.stderr)
            sys.exit(1)
        if parsed.proc_exitcodes:
            codes = [int(c.strip()) for c in parsed.proc_exitcodes.split(",")]
            if parsed.proc_num >= len(codes):
                print(f"--proc-num {parsed.proc_num} is out of range for --proc-exitcodes ({len(codes)} entries)", file=sys.stderr)
                sys.exit(1)
            parsed.exitcode = codes[parsed.proc_num]
        if parsed.proc_sleeps:
            sleeps = [float(s.strip()) for s in parsed.proc_sleeps.split(",")]
            if parsed.proc_num >= len(sleeps):
                print(f"--proc-num {parsed.proc_num} is out of range for --proc-sleeps ({len(sleeps)} entries)", file=sys.stderr)
                sys.exit(1)
            parsed.sleep = sleeps[parsed.proc_num]

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
    
    if parsed.exitcode is not None:
        sys.exit(parsed.exitcode)


if __name__ == "__main__":
    main()
