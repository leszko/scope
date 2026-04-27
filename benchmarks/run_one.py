"""Run a single benchmark configuration and write results to JSON.

Designed to be invoked as a subprocess so each run has a clean import state
(important: SageAttention vs FlashAttention 2 is selected at import time based
on the DISABLE_SAGEATTENTION env var).
"""

import argparse
import gc
import json
import os
import time
import traceback
from pathlib import Path

import torch


def get_attention_backend() -> str:
    """Report which attention backend is actually active after import."""
    try:
        from scope.core.pipelines.wan2_1.modules.attention import (
            FLASH_ATTN_2_AVAILABLE,
            FLASH_ATTN_3_AVAILABLE,
            SAGEATTN_AVAILABLE,
        )
    except Exception:
        return "unknown"
    if SAGEATTN_AVAILABLE:
        return "sageattention"
    if FLASH_ATTN_3_AVAILABLE:
        return "flash_attention_3"
    if FLASH_ATTN_2_AVAILABLE:
        return "flash_attention_2"
    return "torch_sdpa"


def run_streamdiffusionv2(config_dict, num_chunks: int, results: dict) -> None:
    from omegaconf import OmegaConf

    from scope.core.config import get_model_file_path, get_models_dir
    from scope.core.pipelines.streamdiffusionv2.pipeline import (
        StreamDiffusionV2Pipeline,
    )
    from scope.core.pipelines.video import load_video

    chunk_size = 4
    start_chunk_size = 5

    from scope.core.pipelines.enums import Quantization

    cfg = OmegaConf.create(
        {
            "model_dir": str(get_models_dir()),
            "generator_path": str(
                get_model_file_path("StreamDiffusionV2/wan_causal_dmd_v2v/model.pt")
            ),
            "text_encoder_path": str(
                get_model_file_path(
                    "WanVideo_comfy/umt5-xxl-enc-fp8_e4m3fn.safetensors"
                )
            ),
            "tokenizer_path": str(
                get_model_file_path("Wan2.1-T2V-1.3B/google/umt5-xxl")
            ),
            "model_config": OmegaConf.load(
                Path(
                    "/home/user/scope/src/scope/core/pipelines/streamdiffusionv2/model.yaml"
                )
            ),
            "height": config_dict["height"],
            "width": config_dict["width"],
            "vae_type": config_dict["vae"],
        }
    )

    quantization = (
        Quantization.FP8_E4M3FN if config_dict["quant"] == "fp8_e4m3fn" else None
    )

    device = torch.device("cuda")
    torch.cuda.reset_peak_memory_stats()

    t0 = time.time()
    pipeline = StreamDiffusionV2Pipeline(
        cfg, device=device, dtype=torch.bfloat16, quantization=quantization
    )
    load_time = time.time() - t0
    torch.cuda.synchronize()
    results["load_time_sec"] = load_time
    results["post_load_vram_mb"] = torch.cuda.memory_allocated() / (1024 ** 2)

    # Input video
    input_video = (
        load_video(
            Path(
                "/home/user/scope/src/scope/core/pipelines/streamdiffusionv2/assets/original.mp4"
            ),
            resize_hw=(config_dict["height"], config_dict["width"]),
        )
        .unsqueeze(0)
        .to("cuda", torch.bfloat16)
    )
    _, _, num_frames, _, _ = input_video.shape
    max_chunks = max((num_frames - 1) // chunk_size, 1)
    num_chunks = min(num_chunks, max_chunks)

    prompts = [{"text": "a bear is walking on the grass", "weight": 100}]

    latencies = []
    frames_per_chunk = []
    first_call_latency = None

    start_idx = 0
    end_idx = start_chunk_size
    for i in range(num_chunks):
        if i > 0:
            start_idx = end_idx
            end_idx = end_idx + chunk_size
        chunk = input_video[:, :, start_idx:end_idx]
        torch.cuda.synchronize()
        t = time.time()
        out = pipeline(video=chunk, prompts=prompts)
        torch.cuda.synchronize()
        dt = time.time() - t
        nof = out["video"].shape[0]
        if first_call_latency is None:
            first_call_latency = dt
        latencies.append(dt)
        frames_per_chunk.append(nof)
        print(f"chunk {i}: {dt:.3f}s ({nof} frames -> {nof / dt:.2f} fps)")

    results["first_call_latency_sec"] = first_call_latency
    results["per_chunk_latencies_sec"] = latencies
    results["frames_per_chunk"] = frames_per_chunk
    results["peak_vram_mb"] = torch.cuda.max_memory_allocated() / (1024 ** 2)


def run_text_pipeline(
    pipeline_id: str,
    config_dict: dict,
    num_chunks: int,
    results: dict,
) -> None:
    """Run a text-to-video pipeline (LongLive, MemFlow, RewardForcing)."""
    from omegaconf import OmegaConf

    from scope.core.config import get_model_file_path, get_models_dir

    device = torch.device("cuda")

    if pipeline_id == "longlive":
        from scope.core.pipelines.longlive.pipeline import LongLivePipeline as Pipeline

        generator_path = get_model_file_path(
            "LongLive-1.3B/models/longlive_base.pt"
        )
        lora_path = get_model_file_path("LongLive-1.3B/models/lora.pt")
        model_yaml = Path(
            "/home/user/scope/src/scope/core/pipelines/longlive/model.yaml"
        )
        extra = {"lora_path": str(lora_path)}
    elif pipeline_id == "memflow":
        from scope.core.pipelines.memflow.pipeline import MemFlowPipeline as Pipeline

        generator_path = get_model_file_path("MemFlow/base.pt")
        lora_path = get_model_file_path("MemFlow/lora.pt")
        model_yaml = Path(
            "/home/user/scope/src/scope/core/pipelines/memflow/model.yaml"
        )
        extra = {"lora_path": str(lora_path)}
    elif pipeline_id == "reward_forcing":
        from scope.core.pipelines.reward_forcing.pipeline import (
            RewardForcingPipeline as Pipeline,
        )

        generator_path = get_model_file_path(
            "Reward-Forcing-T2V-1.3B/rewardforcing.pt"
        )
        model_yaml = Path(
            "/home/user/scope/src/scope/core/pipelines/reward_forcing/model.yaml"
        )
        extra = {}
    else:
        raise ValueError(f"Unknown text pipeline: {pipeline_id}")

    from scope.core.pipelines.enums import Quantization

    cfg_dict = {
        "model_dir": str(get_models_dir()),
        "generator_path": str(generator_path),
        "text_encoder_path": str(
            get_model_file_path("WanVideo_comfy/umt5-xxl-enc-fp8_e4m3fn.safetensors")
        ),
        "tokenizer_path": str(get_model_file_path("Wan2.1-T2V-1.3B/google/umt5-xxl")),
        "model_config": OmegaConf.load(model_yaml),
        "height": config_dict["height"],
        "width": config_dict["width"],
        "vae_type": config_dict["vae"],
        **extra,
    }
    cfg = OmegaConf.create(cfg_dict)
    quantization = (
        Quantization.FP8_E4M3FN if config_dict["quant"] == "fp8_e4m3fn" else None
    )

    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    pipeline = Pipeline(
        cfg, device=device, dtype=torch.bfloat16, quantization=quantization
    )
    load_time = time.time() - t0
    torch.cuda.synchronize()
    results["load_time_sec"] = load_time
    results["post_load_vram_mb"] = torch.cuda.memory_allocated() / (1024 ** 2)

    prompt_text = (
        "A realistic video of a person walking across a park on a sunny day. "
        "The camera slowly tracks them, trees and grass in the background. "
        "Cinematic lighting. Wide shot."
    )
    prompts = [{"text": prompt_text, "weight": 100}]

    latencies = []
    frames_per_chunk = []
    first_call_latency = None

    for i in range(num_chunks):
        torch.cuda.synchronize()
        t = time.time()
        out = pipeline(prompts=prompts, init_cache=(i == 0))
        torch.cuda.synchronize()
        dt = time.time() - t
        nof = out["video"].shape[0]
        if first_call_latency is None:
            first_call_latency = dt
        latencies.append(dt)
        frames_per_chunk.append(nof)
        print(f"chunk {i}: {dt:.3f}s ({nof} frames -> {nof / dt:.2f} fps)")

    results["first_call_latency_sec"] = first_call_latency
    results["per_chunk_latencies_sec"] = latencies
    results["frames_per_chunk"] = frames_per_chunk
    results["peak_vram_mb"] = torch.cuda.max_memory_allocated() / (1024 ** 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pipeline",
        required=True,
        choices=["streamdiffusionv2", "longlive", "memflow", "reward_forcing"],
    )
    ap.add_argument("--quant", default="none", choices=["none", "fp8_e4m3fn"])
    ap.add_argument(
        "--vae",
        default="wan",
        choices=["wan", "lightvae", "tae", "lighttae"],
    )
    ap.add_argument("--resolution", default=None, help="HxW like 320x576")
    ap.add_argument("--num-chunks", type=int, default=8)
    ap.add_argument("--output", required=True, help="Path to write JSON result")
    args = ap.parse_args()

    # Resolution defaults per pipeline
    if args.resolution is None:
        if args.pipeline == "streamdiffusionv2":
            h, w = 480, 832
        else:
            h, w = 480, 832
    else:
        h, w = map(int, args.resolution.lower().split("x"))

    config_dict = {
        "height": h,
        "width": w,
        "vae": args.vae,
        "quant": args.quant,
    }

    results = {
        "pipeline": args.pipeline,
        "quant": args.quant,
        "vae": args.vae,
        "height": h,
        "width": w,
        "num_chunks_requested": args.num_chunks,
        "disable_sageattention": os.getenv("DISABLE_SAGEATTENTION", "0"),
    }

    try:
        # Import attention module to resolve backend
        import scope.core.pipelines.wan2_1.modules.attention  # noqa: F401

        results["attention_backend"] = get_attention_backend()
        results["gpu_name"] = torch.cuda.get_device_name(0)
        results["gpu_compute_cap"] = "{}.{}".format(*torch.cuda.get_device_capability(0))
        results["total_vram_mb"] = (
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        )

        if args.pipeline == "streamdiffusionv2":
            run_streamdiffusionv2(config_dict, args.num_chunks, results)
        else:
            run_text_pipeline(args.pipeline, config_dict, args.num_chunks, results)

        # Compute summary stats
        lat = results["per_chunk_latencies_sec"]
        frames = results["frames_per_chunk"]
        # Skip first chunk when computing steady-state stats (it includes warmup)
        lat_steady = lat[1:] if len(lat) > 1 else lat
        frames_steady = frames[1:] if len(frames) > 1 else frames
        if lat_steady:
            import statistics

            per_frame_latencies = []
            for li, fi in zip(lat_steady, frames_steady):
                if fi > 0:
                    per_frame_latencies.append(li / fi)
            results["steady_mean_chunk_sec"] = statistics.mean(lat_steady)
            results["steady_median_chunk_sec"] = statistics.median(lat_steady)
            if len(lat_steady) >= 2:
                results["steady_stdev_chunk_sec"] = statistics.stdev(lat_steady)
            total_frames = sum(frames_steady)
            total_time = sum(lat_steady)
            results["steady_fps"] = total_frames / total_time if total_time > 0 else 0
            if per_frame_latencies:
                sorted_pf = sorted(per_frame_latencies)
                results["per_frame_p50_ms"] = (
                    statistics.median(per_frame_latencies) * 1000
                )
                p95_idx = int(len(sorted_pf) * 0.95)
                p95_idx = min(p95_idx, len(sorted_pf) - 1)
                p99_idx = int(len(sorted_pf) * 0.99)
                p99_idx = min(p99_idx, len(sorted_pf) - 1)
                results["per_frame_p95_ms"] = sorted_pf[p95_idx] * 1000
                results["per_frame_p99_ms"] = sorted_pf[p99_idx] * 1000
                results["per_frame_mean_ms"] = (
                    statistics.mean(per_frame_latencies) * 1000
                )

        results["success"] = True
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)
        results["traceback"] = traceback.format_exc()
        print(f"FAILED: {e}")
        traceback.print_exc()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Wrote {args.output}")

    # Cleanup
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
