"""Orchestrator: runs all benchmark configurations as subprocesses.

Each subprocess has a clean Python import state so SageAttention vs
FlashAttention 2 can be selected via the DISABLE_SAGEATTENTION env var.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/user/scope")
RESULTS_DIR = REPO / "benchmarks" / "results"
RUNNER = REPO / "benchmarks" / "run_one.py"

# Timeout per run: load can take 90s; 8 chunks typically < 90s.
TIMEOUT_SEC = 600


def run_case(name: str, args: list[str], env: dict, num_chunks: int):
    """Run a single benchmark case as a subprocess."""
    out = RESULTS_DIR / f"{name}.json"
    if out.exists():
        print(f"[skip] {name} (exists)")
        return
    print(f"\n{'=' * 70}\n[run ] {name}\n{'=' * 70}")
    full_env = {**os.environ, **env}
    cmd = [
        "uv", "run", "python", str(RUNNER),
        *args,
        "--num-chunks", str(num_chunks),
        "--output", str(out),
    ]
    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            env=full_env,
            cwd=str(REPO),
            timeout=TIMEOUT_SEC,
            capture_output=False,
        )
        print(f"[done] {name} (rc={res.returncode}, {time.time() - t0:.0f}s)")
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {name} after {TIMEOUT_SEC}s")
        with open(out, "w") as f:
            json.dump(
                {"pipeline": name, "success": False, "error": "timeout"}, f, indent=2
            )


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    pipelines = ["streamdiffusionv2", "longlive", "memflow", "reward_forcing"]
    # Resolution: use 512x512 for all pipelines so numbers are comparable
    default_res = "512x512"

    num_chunks = 8

    # Matrix: Each pipeline × {baseline, fa2, fp8, lightvae, lightvae+fp8}
    # Baseline = SageAttention + BF16 + WAN VAE
    matrix = []

    # Head-to-head: all 4 pipelines at default (SageAttn, BF16, WAN VAE, 512x512)
    for p in pipelines:
        matrix.append(
            (
                f"{p}__baseline",
                ["--pipeline", p, "--quant", "none", "--vae", "wan", "--resolution", default_res],
                {},
            )
        )

    # Attention A/B: force FA2 on all pipelines
    for p in pipelines:
        matrix.append(
            (
                f"{p}__fa2",
                ["--pipeline", p, "--quant", "none", "--vae", "wan", "--resolution", default_res],
                {"DISABLE_SAGEATTENTION": "1"},
            )
        )

    # FP8 quantization on all pipelines (SageAttn)
    for p in pipelines:
        matrix.append(
            (
                f"{p}__fp8",
                ["--pipeline", p, "--quant", "fp8_e4m3fn", "--vae", "wan", "--resolution", default_res],
                {},
            )
        )

    # LightVAE (SageAttn, BF16)
    for p in pipelines:
        matrix.append(
            (
                f"{p}__lightvae",
                ["--pipeline", p, "--quant", "none", "--vae", "lightvae", "--resolution", default_res],
                {},
            )
        )

    # LightVAE + FP8 combined
    for p in pipelines:
        matrix.append(
            (
                f"{p}__lightvae_fp8",
                ["--pipeline", p, "--quant", "fp8_e4m3fn", "--vae", "lightvae", "--resolution", default_res],
                {},
            )
        )

    # Resolution scan on StreamDiffusionV2 (baseline-ish config)
    for res in ["320x576", "480x832"]:
        matrix.append(
            (
                f"streamdiffusionv2__res_{res}",
                [
                    "--pipeline", "streamdiffusionv2",
                    "--quant", "none",
                    "--vae", "wan",
                    "--resolution", res,
                ],
                {},
            )
        )

    print(f"\nTotal runs: {len(matrix)}")
    print(f"Results dir: {RESULTS_DIR}\n")

    for name, args, env in matrix:
        run_case(name, args, env, num_chunks)

    # Print summary
    print("\n\nSUMMARY")
    print("=" * 80)
    for f in sorted(RESULTS_DIR.glob("*.json")):
        with open(f) as fh:
            d = json.load(fh)
        if d.get("success"):
            fps = d.get("steady_fps", 0)
            vram = d.get("peak_vram_mb", 0)
            attn = d.get("attention_backend", "?")
            p99 = d.get("per_frame_p99_ms", 0)
            print(
                f"  {f.stem:<45} attn={attn:<15} "
                f"fps={fps:>5.2f} p99={p99:>7.1f}ms vram={vram:>7.0f}MB"
            )
        else:
            err = (d.get("error") or "")[:60]
            print(f"  {f.stem:<45} FAIL: {err}")


if __name__ == "__main__":
    main()
