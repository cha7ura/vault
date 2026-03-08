#!/usr/bin/env python3
"""
People Agents Pipeline Runner.

Orchestrates the four pipeline stages in sequence.

Usage:
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --nemo-dir /path/to/output
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --stage build
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --stage build --resume
"""

import argparse
import subprocess
import sys
import time


def run_stage(stage_module: str, args: list[str]):
    """Run a pipeline stage as a subprocess."""
    cmd = [sys.executable, "-m", stage_module] + args
    print(f"\n{'='*60}")
    print(f"Stage: {stage_module}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    t_start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t_start

    if result.returncode != 0:
        print(f"\nERROR: {stage_module} exited with code {result.returncode}")
        print(f"Elapsed: {elapsed:.1f}s")
        sys.exit(result.returncode)

    print(f"\nCompleted {stage_module} in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="People Agents Pipeline Runner")
    parser.add_argument("--channel", required=True, help="Channel slug")
    parser.add_argument("--nemo-dir", help="NeMo output directory (required for extract stage)")
    parser.add_argument(
        "--stage",
        choices=["extract", "map", "build", "export", "all"],
        default="all",
        help="Which stage to run (default: all)",
    )
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap host identification")
    parser.add_argument("--resume", action="store_true", help="Resume build_memory from checkpoint")
    parser.add_argument("--person-slug", help="Process single person (for build/export)")
    args = parser.parse_args()

    # Build stage-specific args
    extract_args = ["--nemo-dir", args.nemo_dir or ""]
    map_args = ["--channel", args.channel] + (["--bootstrap"] if args.bootstrap else [])
    build_args = (
        ["--channel", args.channel]
        + (["--resume"] if args.resume else [])
        + (["--person-slug", args.person_slug] if args.person_slug else [])
    )
    export_args = ["--channel", args.channel] + (
        ["--person-slug", args.person_slug] if args.person_slug else []
    )

    stages = {
        "extract": ("scripts.agents.extract_embeddings", extract_args),
        "map": ("scripts.agents.map_speakers", map_args),
        "build": ("scripts.agents.build_memory", build_args),
        "export": ("scripts.agents.export_memory", export_args),
    }

    if args.stage == "all":
        if not args.nemo_dir:
            print("ERROR: --nemo-dir required when running all stages")
            sys.exit(1)
        for stage_name in ["extract", "map", "build", "export"]:
            run_stage(*stages[stage_name])
    else:
        if args.stage == "extract" and not args.nemo_dir:
            print("ERROR: --nemo-dir required for extract stage")
            sys.exit(1)
        module, stage_args = stages[args.stage]
        run_stage(module, stage_args)

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
