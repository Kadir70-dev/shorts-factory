"""Hardware detection for Blender render-setting selection (brief section
14: "Detect available hardware before selecting renderer/settings").

Verified against THIS machine (2026-08-22): a single Intel Iris Plus
Graphics 640 integrated GPU (1GB shared VRAM), no discrete/CUDA/OptiX
device. That is NOT a GPU Cycles (path-tracing) can meaningfully
accelerate -- Blender's Cycles GPU backends target CUDA/OptiX (NVIDIA) or
HIP (AMD); Iris Plus has no supported backend, so Cycles would silently
fall back to (slow) CPU compute anyway. `recommend()` below reflects that
honestly: EEVEE (rasterized, real-time-oriented) at CPU-friendly sample
counts, not Cycles, on hardware like this.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class HardwareProfile:
    gpu_name: str
    gpu_vram_mb: int
    cuda_or_optix_capable: bool
    recommended_engine: str      # "BLENDER_EEVEE_NEXT" | "CYCLES"
    recommended_device: str      # "CPU" | "GPU"
    max_samples: int
    notes: str


def detect() -> HardwareProfile:
    gpu_name = "unknown"
    vram_mb = 0
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        import json as _json
        info = _json.loads(out)
        gpu_name = info.get("Name", "unknown")
        vram_mb = int((info.get("AdapterRAM") or 0) / (1024 * 1024))
    except Exception:
        pass

    cuda_capable = any(v in gpu_name for v in ("NVIDIA", "GeForce", "RTX", "Quadro"))
    hip_capable = "Radeon" in gpu_name and "RX" in gpu_name

    if cuda_capable or hip_capable:
        return HardwareProfile(
            gpu_name=gpu_name, gpu_vram_mb=vram_mb, cuda_or_optix_capable=True,
            recommended_engine="CYCLES", recommended_device="GPU", max_samples=128,
            notes="Discrete GPU with a Cycles-supported backend detected.",
        )
    return HardwareProfile(
        gpu_name=gpu_name, gpu_vram_mb=vram_mb, cuda_or_optix_capable=False,
        recommended_engine="BLENDER_EEVEE_NEXT", recommended_device="CPU", max_samples=32,
        notes=(
            f"'{gpu_name}' has no Cycles-supported GPU backend (needs CUDA/OptiX/HIP). "
            "Recommending EEVEE at low sample counts on CPU to keep per-scene render "
            "time in the seconds-to-low-minutes range instead of Cycles' "
            "many-minutes-to-hours on integrated graphics."
        ),
    )
