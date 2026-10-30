#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from pathlib import Path
import grp
import os
import pwd
import random
import stat
import subprocess
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


# The prompt itself is fixed in code rather than taken as an argument - this flag only ever
# needs to prove the mounted model is present and loadable, not exercise arbitrary prompts.
# The two numbers added are configurable so the expected answer can be varied per run.
_AI_MODEL_PROMPT_TEMPLATE = "What is {a} + {b}? Respond with only the number, nothing else."
_AI_MODEL_MAX_NEW_TOKENS = 64
# stdout for this script is only captured by the CTS when the container fails, so the actual
# query result is also written here, as a job output file, to be retrievable on success too.
# Written under --ai-model-output-dir, not the working directory, since the working directory
# has no guaranteed relationship to the job's output mount point - see Parameters.output_mount_point
# in the CTS, whose default this mirrors.
_AI_MODEL_RESPONSE_FILE = "prompt_response.md"
_DEFAULT_AI_MODEL_OUTPUT_DIR = "/output_files"


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


def print_gpu_info() -> None:
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("nvidia-smi output:")
            print(result.stdout.rstrip())
        else:
            print(f"nvidia-smi error: {result.stderr.rstrip()}")
    except FileNotFoundError:
        print("nvidia-smi: not found")
    except subprocess.TimeoutExpired:
        print("nvidia-smi: timed out")

    print(f"PyTorch version: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA available: {cuda_available}")
    if cuda_available:
        print(f"CUDA version: {torch.version.cuda}")
        count = torch.cuda.device_count()
        print(f"GPU count: {count}")
        for i in range(count):
            props = torch.cuda.get_device_properties(i)
            mem_gb = props.total_memory / 1024 ** 3
            print(f"  GPU {i}: {props.name}, {mem_gb:.1f} GB")


def run_gpu_task() -> None:
    if not torch.cuda.is_available():
        print("GPU task: no CUDA GPUs available", file=sys.stderr)
        sys.exit(1)
    size = 4096
    print(f"GPU task: {size}x{size} float32 matrix multiply on GPU 0 ...", flush=True)
    a = torch.randn(size, size, device="cuda")
    b = torch.randn(size, size, device="cuda")
    c = torch.mm(a, b)
    torch.cuda.synchronize()
    print(f"GPU task: done, result checksum {c.sum().item():.4f}")


def run_ai_model_query(
    model_path: str, a: int, b: int, output_dir: str, force_cuda: bool = False
) -> None:
    """
    Load a model and tokenizer from a local directory (e.g. a mounted AI model store path)
    and run one fixed, deterministic text generation against it, writing the result to both
    stdout and _AI_MODEL_RESPONSE_FILE under output_dir. This only ever prints/writes the
    model's output as inert text - it is never passed to exec/eval/a shell or otherwise
    interpreted as code or instructions, so there's no path by which the model's own output
    could run arbitrary code in this image.

    a, b - the two integers to add in the prompt.
    output_dir - the directory in which to write _AI_MODEL_RESPONSE_FILE. Must match the job's
        output mount point for the file to actually be collected as a job output - the
        working directory has no guaranteed relationship to that mount point.
    force_cuda - use "cuda" unconditionally rather than falling back to "cpu" when CUDA isn't
        available, so a run on a node that unexpectedly has no GPU fails loudly instead of
        silently succeeding on the CPU - useful for confirming GPU scheduling actually worked.
    """
    prompt = _AI_MODEL_PROMPT_TEMPLATE.format(a=a, b=b)
    print(f"AI model query: loading model from {model_path} ...", flush=True)
    # local_files_only ensures this can only ever use what's actually mounted at model_path -
    # if staging/mounting is broken, this fails loudly instead of silently falling back to a
    # network fetch and masking the problem.
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(model_path, local_files_only=True)

    device = "cuda" if (force_cuda or torch.cuda.is_available()) else "cpu"
    print(f"AI model query: running on {device}", flush=True)
    model = model.to(device)
    model.eval()

    messages = [{"role": "user", "content": prompt}]
    template_kwargs = dict(
        add_generation_prompt=True, return_tensors="pt", return_dict=True,
    )
    try:
        # enable_thinking=False keeps the output a direct answer for models (e.g. Qwen3) that
        # otherwise emit a <think>...</think> preamble by default.
        inputs = tokenizer.apply_chat_template(
            messages, enable_thinking=False, **template_kwargs,
        )
    except TypeError:
        # Not every chat template understands enable_thinking - fall back without it.
        inputs = tokenizer.apply_chat_template(messages, **template_kwargs)
    inputs = inputs.to(device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=_AI_MODEL_MAX_NEW_TOKENS,
            do_sample=False,
        )
    response = tokenizer.decode(
        output_ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True
    )

    content = (
        "# AI model query result\n\n"
        f"Model path: {model_path}\n\n"
        f"Device: {device}\n\n"
        f"Prompt: {prompt}\n\n"
        f"Response:\n\n{response}\n"
    )
    print(content, flush=True)
    response_path = Path(output_dir) / _AI_MODEL_RESPONSE_FILE
    response_path.write_text(content)
    print(f"AI model query: wrote response to {response_path}", flush=True)


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
        "-G", "--gpu-task",
        action="store_true",
        help="Run a small GPU matrix multiply to confirm CUDA compute is working"
    )

    parser.add_argument(
        "-Q", "--ai-model-query",
        metavar="MODEL_DIRECTORY",
        help="Load a model from the given local directory (e.g. a mounted AI model store "
             f"path) and run a fixed query against it, writing the result to stdout and "
             f"{_AI_MODEL_RESPONSE_FILE}"
    )
    parser.add_argument(
        "--ai-model-output-dir",
        metavar="DIRECTORY",
        default=_DEFAULT_AI_MODEL_OUTPUT_DIR,
        help="Directory to write the --ai-model-query response file to - must match the "
             f"job's output_mount_point for it to be collected as a job output "
             f"(default: {_DEFAULT_AI_MODEL_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--ai-model-numbers",
        nargs=2,
        type=int,
        default=[2, 2],
        metavar=("A", "B"),
        help="The two integers to add in the --ai-model-query prompt (default: 2 2)"
    )
    parser.add_argument(
        "--force-cuda",
        action="store_true",
        help="Use cuda unconditionally for --ai-model-query instead of falling back to cpu "
             "when unavailable, so the run fails loudly if cuda was requested but the node "
             "doesn't actually have a GPU"
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
    print("Start time:", datetime.now(timezone.utc).isoformat())
    print_gpu_info()

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
        print(f"Random roll: {roll:.4f} (run<{w_run}, fail<{w_run + w_fail}, complete<={1.0})")
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

    if parsed.gpu_task:
        run_gpu_task()

    if parsed.ai_model_query:
        try:
            run_ai_model_query(
                parsed.ai_model_query,
                *parsed.ai_model_numbers,
                parsed.ai_model_output_dir,
                force_cuda=parsed.force_cuda,
            )
        except Exception as e:
            print(f"AI model query failed: {e}", file=sys.stderr)
            sys.exit(1)

    if parsed.sleep is not None:
        time.sleep(parsed.sleep)
    
    if parsed.exitcode is not None:
        sys.exit(parsed.exitcode)


if __name__ == "__main__":
    main()
