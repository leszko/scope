"""Generate charts from benchmark JSON results."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path("/home/user/scope")
RESULTS = REPO / "benchmarks" / "results"
IMAGES = REPO / "benchmarks" / "images"
IMAGES.mkdir(parents=True, exist_ok=True)


PIPELINES = ["streamdiffusionv2", "longlive", "memflow", "reward_forcing"]
PIPELINE_LABELS = {
    "streamdiffusionv2": "StreamDiffusionV2",
    "longlive": "LongLive",
    "memflow": "MemFlow",
    "reward_forcing": "RewardForcing",
}
CONFIG_ORDER = ["baseline", "fa2", "fp8", "lightvae", "lightvae_fp8"]
CONFIG_LABELS = {
    "baseline": "SageAttn · BF16 · Full VAE",
    "fa2": "FlashAttn2 · BF16 · Full VAE",
    "fp8": "SageAttn · FP8 · Full VAE",
    "lightvae": "SageAttn · BF16 · LightVAE",
    "lightvae_fp8": "SageAttn · FP8 · LightVAE",
}
CONFIG_COLORS = {
    "baseline": "#1f77b4",
    "fa2": "#ff7f0e",
    "fp8": "#2ca02c",
    "lightvae": "#d62728",
    "lightvae_fp8": "#9467bd",
}


def load_results() -> dict:
    results = {}
    for f in RESULTS.glob("*.json"):
        with open(f) as fh:
            d = json.load(fh)
        results[f.stem] = d
    return results


def _bar(ax, groups, values_by_config, ylabel, title, fmt="{:.1f}"):
    x = np.arange(len(groups))
    n_configs = len(CONFIG_ORDER)
    width = 0.8 / n_configs
    for i, config in enumerate(CONFIG_ORDER):
        heights = [values_by_config.get(config, {}).get(g, 0) for g in groups]
        bars = ax.bar(
            x + (i - n_configs / 2 + 0.5) * width,
            heights,
            width,
            label=CONFIG_LABELS[config],
            color=CONFIG_COLORS[config],
            edgecolor="black",
            linewidth=0.5,
        )
        for rect, h in zip(bars, heights):
            if h > 0:
                ax.text(
                    rect.get_x() + rect.get_width() / 2,
                    h,
                    fmt.format(h),
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )
    ax.set_xticks(x)
    ax.set_xticklabels([PIPELINE_LABELS[g] for g in groups], rotation=0)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)


def plot_fps(results):
    """Hero chart: FPS by pipeline × config."""
    fig, ax = plt.subplots(figsize=(12, 6))
    values = {config: {} for config in CONFIG_ORDER}
    for p in PIPELINES:
        for config in CONFIG_ORDER:
            key = f"{p}__{config}"
            if key in results and results[key].get("success"):
                values[config][p] = results[key].get("steady_fps", 0)
    _bar(ax, PIPELINES, values, "Steady-state FPS", "Real-time video diffusion throughput on RTX 5090 (512×512, BF16 unless marked)")
    ax.axhline(24, color="gray", linestyle=":", linewidth=1, label="24 fps real-time target")
    ax.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(IMAGES / "hero_fps.png", dpi=140)
    print(f"saved {IMAGES / 'hero_fps.png'}")
    plt.close()


def plot_vram(results):
    fig, ax = plt.subplots(figsize=(12, 6))
    values = {config: {} for config in CONFIG_ORDER}
    for p in PIPELINES:
        for config in CONFIG_ORDER:
            key = f"{p}__{config}"
            if key in results and results[key].get("success"):
                values[config][p] = results[key].get("peak_vram_mb", 0) / 1024
    _bar(ax, PIPELINES, values, "Peak VRAM (GB)", "Peak VRAM usage by pipeline × config (RTX 5090, 32 GB)", fmt="{:.1f}")
    ax.axhline(32, color="red", linestyle=":", linewidth=1, label="RTX 5090 limit (32 GB)")
    ax.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(IMAGES / "vram.png", dpi=140)
    print(f"saved {IMAGES / 'vram.png'}")
    plt.close()


def plot_per_frame_latency(results):
    fig, ax = plt.subplots(figsize=(12, 6))
    values = {config: {} for config in CONFIG_ORDER}
    for p in PIPELINES:
        for config in CONFIG_ORDER:
            key = f"{p}__{config}"
            if key in results and results[key].get("success"):
                values[config][p] = results[key].get("per_frame_p99_ms", 0)
    _bar(ax, PIPELINES, values, "p99 per-frame latency (ms)", "p99 per-frame latency on RTX 5090", fmt="{:.0f}")
    ax.axhline(1000 / 24, color="gray", linestyle=":", linewidth=1, label="24 fps budget (41.7 ms/frame)")
    ax.legend(loc="upper left", fontsize=8)
    plt.tight_layout()
    plt.savefig(IMAGES / "per_frame_p99.png", dpi=140)
    print(f"saved {IMAGES / 'per_frame_p99.png'}")
    plt.close()


def plot_attention_delta(results):
    """SageAttn vs FA2 side-by-side comparison."""
    fig, ax = plt.subplots(figsize=(10, 5))
    pipelines = []
    sage_fps = []
    fa2_fps = []
    for p in PIPELINES:
        sage_key = f"{p}__baseline"
        fa2_key = f"{p}__fa2"
        if (
            sage_key in results
            and fa2_key in results
            and results[sage_key].get("success")
            and results[fa2_key].get("success")
        ):
            pipelines.append(PIPELINE_LABELS[p])
            sage_fps.append(results[sage_key]["steady_fps"])
            fa2_fps.append(results[fa2_key]["steady_fps"])

    x = np.arange(len(pipelines))
    width = 0.36
    b1 = ax.bar(
        x - width / 2, sage_fps, width,
        label="SageAttention 2.2.0", color="#1f77b4", edgecolor="black", linewidth=0.5,
    )
    b2 = ax.bar(
        x + width / 2, fa2_fps, width,
        label="FlashAttention 2.8.3", color="#ff7f0e", edgecolor="black", linewidth=0.5,
    )
    for b, v in zip(b1, sage_fps):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    for b, v in zip(b2, fa2_fps):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(pipelines)
    ax.set_ylabel("Steady-state FPS")
    ax.set_title("SageAttention vs FlashAttention 2 — RTX 5090, 512×512, Wan2.1-1.3B base")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(IMAGES / "attention_delta.png", dpi=140)
    print(f"saved {IMAGES / 'attention_delta.png'}")
    plt.close()


def plot_resolution(results):
    """How does SDv2 scale with resolution?"""
    fig, ax = plt.subplots(figsize=(9, 5))
    entries = []
    for key, d in results.items():
        if not d.get("success"):
            continue
        if not key.startswith("streamdiffusionv2"):
            continue
        # baseline is 512x512, res_HxW keys
        if "res_" in key:
            label = key.split("res_")[1]
        elif key == "streamdiffusionv2__baseline":
            label = "512x512"
        else:
            continue
        entries.append((label, d["height"] * d["width"], d["steady_fps"], d["peak_vram_mb"] / 1024))
    entries.sort(key=lambda x: x[1])
    labels = [e[0] for e in entries]
    fps_vals = [e[2] for e in entries]
    vram_vals = [e[3] for e in entries]
    x = np.arange(len(labels))

    ax.bar(x, fps_vals, color="#1f77b4", edgecolor="black", linewidth=0.5)
    for xi, fv, vv in zip(x, fps_vals, vram_vals):
        ax.text(xi, fv, f"{fv:.1f} fps\n{vv:.1f} GB", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Steady-state FPS")
    ax.set_title("StreamDiffusionV2 — FPS by resolution (SageAttn · BF16 · Full VAE)")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(IMAGES / "resolution_scan.png", dpi=140)
    print(f"saved {IMAGES / 'resolution_scan.png'}")
    plt.close()


def print_table(results):
    print("\n\n" + "=" * 110)
    print(f"{'Config':<45} {'Attn':<15} {'FPS':>7} {'p50 ms':>8} {'p99 ms':>8} {'VRAM GB':>9} {'Load s':>8}")
    print("=" * 110)
    keys = sorted(results.keys())
    for k in keys:
        d = results[k]
        if d.get("success"):
            print(
                f"{k:<45} {d.get('attention_backend', '?'):<15} "
                f"{d.get('steady_fps', 0):>7.2f} "
                f"{d.get('per_frame_p50_ms', 0):>8.1f} "
                f"{d.get('per_frame_p99_ms', 0):>8.1f} "
                f"{d.get('peak_vram_mb', 0) / 1024:>9.2f} "
                f"{d.get('load_time_sec', 0):>8.1f}"
            )
        else:
            err = (d.get("error") or "")[:60]
            print(f"{k:<45} FAIL: {err}")


def plot_pareto(results):
    """Scatter: FPS vs peak VRAM, highlighting Pareto-optimal points."""
    fig, ax = plt.subplots(figsize=(10, 6))

    pts = []
    for key, d in results.items():
        if not d.get("success"):
            continue
        if "res_" in key:
            continue  # skip resolution variants to keep plot clean
        pipeline = key.split("__")[0]
        config = key.split("__", 1)[1]
        pts.append(
            (d["steady_fps"], d["peak_vram_mb"] / 1024, pipeline, config, key)
        )

    markers = {
        "streamdiffusionv2": "o",
        "longlive": "s",
        "memflow": "^",
        "reward_forcing": "D",
    }

    for fps, vram, pipeline, config, _ in pts:
        ax.scatter(
            vram,
            fps,
            marker=markers.get(pipeline, "x"),
            color=CONFIG_COLORS.get(config, "gray"),
            s=110,
            edgecolor="black",
            linewidth=0.6,
            zorder=3,
        )

    # Annotate star: best config (RewardForcing + LightVAE)
    best_fps = max(pts, key=lambda p: p[0])
    ax.annotate(
        f"★ best: {PIPELINE_LABELS.get(best_fps[2], best_fps[2])}\n"
        f"{CONFIG_LABELS.get(best_fps[3], best_fps[3])}\n"
        f"{best_fps[0]:.1f} fps · {best_fps[1]:.1f} GB",
        xy=(best_fps[1], best_fps[0]),
        xytext=(best_fps[1] + 1.2, best_fps[0] - 3.0),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="black", lw=1.1),
        bbox=dict(boxstyle="round,pad=0.4", fc="#fff7c2", ec="black", lw=0.8),
    )

    ax.axhline(24, color="gray", linestyle=":", linewidth=1)
    ax.text(ax.get_xlim()[1] * 0.98, 24.3, "24 fps real-time", ha="right", fontsize=9, color="gray")

    # Marker legend (pipelines)
    pipeline_handles = [
        plt.Line2D(
            [0], [0], marker=markers[p], color="gray", linestyle="None",
            markersize=10, markeredgecolor="black", label=PIPELINE_LABELS[p],
        )
        for p in PIPELINES
    ]
    # Color legend (configs)
    config_handles = [
        plt.Line2D(
            [0], [0], marker="s", color=CONFIG_COLORS[c], linestyle="None",
            markersize=11, markeredgecolor="black", label=CONFIG_LABELS[c],
        )
        for c in CONFIG_ORDER
    ]
    leg1 = ax.legend(handles=pipeline_handles, title="Pipeline", loc="upper left", fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=config_handles, title="Config", loc="lower right", fontsize=8)

    ax.set_xlabel("Peak VRAM (GB)")
    ax.set_ylabel("Steady-state FPS")
    ax.set_title("FPS vs VRAM — the Pareto frontier (RTX 5090, 512×512)")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(IMAGES / "pareto.png", dpi=140)
    print(f"saved {IMAGES / 'pareto.png'}")
    plt.close()


def main():
    results = load_results()
    print(f"Loaded {len(results)} results")
    plot_fps(results)
    plot_vram(results)
    plot_per_frame_latency(results)
    plot_attention_delta(results)
    plot_resolution(results)
    plot_pareto(results)
    print_table(results)


if __name__ == "__main__":
    main()
