"""Video upscaling module with support for multiple upscaling methods."""

import logging
import os
from enum import Enum

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


# Compatibility patch for py-real-esrgan's outdated huggingface_hub API
def _patch_huggingface_hub():
    """Patch huggingface_hub to provide cached_download for py-real-esrgan compatibility.

    py-real-esrgan uses the old cached_download API which was removed in huggingface_hub 0.26+.
    This patch provides a compatibility wrapper that uses hf_hub_download internally.
    """
    try:
        import huggingface_hub
        from huggingface_hub import hf_hub_download

        # Only patch if cached_download doesn't exist
        if not hasattr(huggingface_hub, "cached_download"):

            def cached_download(
                url_or_repo_id,
                filename=None,
                cache_dir=None,
                force_filename=None,
                **kwargs,
            ):
                """Compatibility wrapper for cached_download using hf_hub_download.

                py-real-esrgan calls: cached_download(url, cache_dir=..., force_filename=...)
                where url is from hf_hub_url() in format: https://huggingface.co/{repo_id}/resolve/main/{filename}
                """
                import shutil
                from urllib.parse import unquote, urlparse

                # Extract repo_id and filename from URL (py-real-esrgan style)
                if (
                    isinstance(url_or_repo_id, str)
                    and "huggingface.co" in url_or_repo_id
                ):
                    parsed = urlparse(url_or_repo_id)
                    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                    if "resolve" in path_parts:
                        resolve_idx = path_parts.index("resolve")
                        repo_id = "/".join(path_parts[:resolve_idx])
                        filename = unquote(
                            "/".join(path_parts[resolve_idx + 2 :])
                        )  # Skip "resolve" and revision
                    else:
                        raise ValueError(
                            f"Cannot parse HuggingFace URL: {url_or_repo_id}"
                        )
                else:
                    # Fallback: assume first arg is repo_id, second is filename
                    repo_id = url_or_repo_id
                    if not filename and len(kwargs) == 0:
                        raise ValueError(
                            "cached_download requires repo_id and filename"
                        )

                # Download using new API
                download_kwargs = {
                    "repo_id": repo_id,
                    "filename": filename,
                    "local_files_only": False,
                }
                if cache_dir:
                    download_kwargs["cache_dir"] = cache_dir

                result = hf_hub_download(**download_kwargs)

                # Copy to force_filename if specified (py-real-esrgan always uses this)
                if force_filename:
                    force_filename = os.path.abspath(force_filename)
                    force_dir = os.path.dirname(force_filename)
                    if force_dir:
                        os.makedirs(force_dir, exist_ok=True)
                    if result != force_filename:
                        shutil.copy2(result, force_filename)
                    return force_filename

                return result

            huggingface_hub.cached_download = cached_download
            logger.debug(
                "Patched huggingface_hub.cached_download for py-real-esrgan compatibility"
            )
    except Exception as e:
        logger.debug(f"Could not patch huggingface_hub: {e}")


# Apply patch on import
_patch_huggingface_hub()


class UpscaleMethod(str, Enum):
    """Upscaling method options.

    Quality implications:
    - BILINEAR/BICUBIC/LANCZOS: Simple interpolation methods. These increase resolution
      but do NOT improve visual quality - they just make the image larger by interpolating
      between existing pixels. Useful for matching output resolution requirements, but
      may appear slightly softer/blurrier than the original.

    - REAL_ESRGAN: AI-based super-resolution model that can actually enhance quality
      by learning to add detail. Significantly slower but produces better results.
      Requires: pip install py-real-esrgan (Python 3.12 compatible) or pip install realesrgan
    """

    BILINEAR = "bilinear"
    BICUBIC = "bicubic"
    REAL_ESRGAN = "realesrgan"
    LANCZOS = "lanczos"


class Upscaler:
    """Upscales video frames using various methods."""

    def __init__(
        self,
        method: UpscaleMethod | str = UpscaleMethod.BICUBIC,
        scale_factor: float = 2.0,
        device: torch.device | None = None,
    ):
        """Initialize upscaler.

        Args:
            method: Upscaling method to use
            scale_factor: Scale factor (e.g., 2.0 for 2x upscaling)
            device: Device to run upscaling on (defaults to CUDA if available)
        """
        self.method = UpscaleMethod(method) if isinstance(method, str) else method
        self.scale_factor = scale_factor
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Lazy load Real-ESRGAN if needed
        self.realesrgan_model = None
        self.realesrgan_scale = None
        if self.method == UpscaleMethod.REAL_ESRGAN:
            self._load_realesrgan()

    def _load_realesrgan(self):
        """Lazy load Real-ESRGAN model."""
        # Try py-real-esrgan first (Python 3.12 compatible)
        try:
            from py_real_esrgan.model import RealESRGAN

            from .models_config import ensure_models_dir

            # Determine scale factor (2x or 4x)
            scale = 4 if self.scale_factor >= 3.5 else 2
            logger.info(
                f"Loading Real-ESRGAN with scale={scale} (requested scale_factor={self.scale_factor})"
            )

            # Use models directory for storing weights
            models_dir = ensure_models_dir()
            weights_dir = models_dir / "realesrgan"
            weights_dir.mkdir(parents=True, exist_ok=True)

            # Use absolute path for weight file
            weight_file = str(weights_dir / f"RealESRGAN_x{scale}.pth")
            logger.debug(f"Real-ESRGAN weight file path: {weight_file}")

            self.realesrgan_model = RealESRGAN(self.device, scale=scale)
            # py-real-esrgan downloads to Hugging Face cache, then copies to specified path
            # If file doesn't exist, it will download and copy it
            # We need to ensure the directory exists first
            self.realesrgan_model.load_weights(weight_file, download=True)

            # Verify the file exists after loading (it should have been downloaded/copied)
            if not os.path.exists(weight_file):
                logger.warning(
                    f"Weight file not found at {weight_file} after download. "
                    "py-real-esrgan may have downloaded to Hugging Face cache instead."
                )
                # Try to find it in the cache
                from huggingface_hub import hf_hub_download

                try:
                    cached_file = hf_hub_download(
                        repo_id="sberbank-ai/Real-ESRGAN",
                        filename=f"RealESRGAN_x{scale}.pth",
                    )
                    # Copy to our desired location
                    import shutil

                    shutil.copy2(cached_file, weight_file)
                    logger.info(f"Copied weight file from cache to {weight_file}")
                    # Reload from the correct location
                    self.realesrgan_model.load_weights(weight_file, download=False)
                except Exception as cache_error:
                    logger.error(
                        f"Failed to find or copy cached weights: {cache_error}"
                    )
                    raise

            self.realesrgan_scale = scale
            logger.info(f"Real-ESRGAN model loaded successfully (scale={scale})")
            return
        except ImportError:
            logger.debug(
                "py-real-esrgan not available, trying original realesrgan package"
            )
        except FileNotFoundError as e:
            # FileNotFoundError might occur if file doesn't exist yet during download
            # Try to find it in Hugging Face cache and copy it
            logger.debug(f"File not found during py-real-esrgan load: {e}")
            try:
                import shutil

                from huggingface_hub import hf_hub_download

                # Try to download from cache
                cached_file = hf_hub_download(
                    repo_id="sberbank-ai/Real-ESRGAN",
                    filename=f"RealESRGAN_x{scale}.pth",
                )
                # Copy to our desired location
                if os.path.exists(cached_file):
                    shutil.copy2(cached_file, weight_file)
                    logger.info(f"Copied weight file from cache to {weight_file}")
                    # Try loading again
                    self.realesrgan_model.load_weights(weight_file, download=False)
                    self.realesrgan_scale = scale
                    logger.info(
                        f"Real-ESRGAN model loaded successfully (scale={scale})"
                    )
                    return
            except Exception as cache_error:
                logger.debug(f"Failed to recover from cache: {cache_error}")
                # Fall through to try original realesrgan package
        except Exception as e:
            logger.warning(
                f"Failed to load py-real-esrgan: {e}, trying original realesrgan package"
            )
            import traceback

            logger.debug(traceback.format_exc())

        # Fallback to original realesrgan package (may not work on Python 3.12)
        try:
            from realesrgan import RealESRGAN

            from .models_config import ensure_models_dir

            # Use RealESRGAN_x4plus model (4x upscaling)
            # For 2x, we can use RealESRGAN_x2plus, but x4plus works for any scale
            scale = 4 if self.scale_factor >= 3.5 else 2

            # Use models directory for storing weights
            models_dir = ensure_models_dir()
            weights_dir = models_dir / "realesrgan"
            weights_dir.mkdir(parents=True, exist_ok=True)

            # Use absolute path for weight file
            weight_file = str(weights_dir / f"RealESRGAN_x{scale}plus.pth")
            logger.debug(f"Real-ESRGAN weight file path: {weight_file}")

            self.realesrgan_model = RealESRGAN(self.device, scale=scale)
            self.realesrgan_model.load_weights(weight_file, download=True)
            self.realesrgan_scale = scale
            logger.info(f"Real-ESRGAN model loaded successfully (scale={scale})")
        except ImportError:
            logger.warning(
                "Real-ESRGAN not available. Install with: pip install py-real-esrgan (Python 3.12) or pip install realesrgan"
            )
            logger.warning("Falling back to bicubic upscaling")
            self.method = UpscaleMethod.BICUBIC
        except Exception as e:
            logger.error(f"Failed to load Real-ESRGAN: {e}")
            logger.warning("Falling back to bicubic upscaling")
            self.method = UpscaleMethod.BICUBIC

    def upscale(
        self,
        frame: torch.Tensor,
        target_height: int | None = None,
        target_width: int | None = None,
    ) -> torch.Tensor:
        """Upscale a single frame.

        Args:
            frame: Input frame tensor in [1, H, W, C] format (uint8 [0, 255])
            target_height: Target height (if None, uses scale_factor)
            target_width: Target width (if None, uses scale_factor)

        Returns:
            Upscaled frame tensor in [1, H', W', C] format (uint8 [0, 255])
        """
        logger.debug(
            f"Upscaler.upscale called: input_shape={frame.shape}, "
            f"target_height={target_height}, target_width={target_width}, "
            f"method={self.method}, scale_factor={self.scale_factor}"
        )

        if frame.dim() != 4 or frame.shape[0] != 1:
            raise ValueError(f"Expected frame shape [1, H, W, C], got {frame.shape}")

        _, height, width, channels = frame.shape

        # Calculate target dimensions
        if target_height is None or target_width is None:
            target_height = int(height * self.scale_factor)
            target_width = int(width * self.scale_factor)
            logger.debug(
                f"Calculated target dimensions from scale: {height}x{width} * {self.scale_factor} = {target_height}x{target_width}"
            )
        else:
            logger.debug(
                f"Using provided target dimensions: {target_width}x{target_height}"
            )

        # If no upscaling needed, return as-is
        if target_height == height and target_width == width:
            logger.debug(f"No upscaling needed: target matches input {height}x{width}")
            return frame

        # Keep frame on its current device (usually GPU for performance)
        # Only move to upscaler device if different and method requires it
        original_device = frame.device
        logger.debug(f"Frame device: {original_device}, upscaler device: {self.device}")
        if self.method == UpscaleMethod.REAL_ESRGAN and frame.device != self.device:
            frame = frame.to(self.device)
            logger.debug(f"Moved frame to {self.device} for Real-ESRGAN")

        logger.debug(
            f"Applying {self.method.value} upscaling: {height}x{width} -> {target_height}x{target_width}"
        )
        if self.method == UpscaleMethod.REAL_ESRGAN:
            result = self._upscale_realesrgan(frame, target_height, target_width)
        else:
            result = self._upscale_interpolation(frame, target_height, target_width)

        logger.debug(f"Upscaling result: {result.shape}, device: {result.device}")

        # Ensure result is on the same device as input
        if result.device != original_device:
            logger.debug(
                f"Moving result from {result.device} back to {original_device}"
            )
            result = result.to(original_device)

        logger.debug(f"Final upscaled frame: {result.shape}, device: {result.device}")
        return result

    def _upscale_interpolation(
        self, frame: torch.Tensor, target_height: int, target_width: int
    ) -> torch.Tensor:
        """Upscale using PyTorch interpolation methods."""
        logger.debug(
            f"_upscale_interpolation: input={frame.shape}, target={target_height}x{target_width}, "
            f"device={frame.device}"
        )
        # Convert from [1, H, W, C] to [1, C, H, W] for interpolation
        # Keep on same device as input (usually GPU)
        frame_chw = frame.permute(0, 3, 1, 2).float()
        logger.debug(f"Permuted to CHW format: {frame_chw.shape}")

        # Choose interpolation mode
        if self.method == UpscaleMethod.BILINEAR:
            mode = "bilinear"
        elif self.method == UpscaleMethod.BICUBIC:
            mode = "bicubic"
        elif self.method == UpscaleMethod.LANCZOS:
            # LANCZOS not directly supported, use bicubic as fallback
            mode = "bicubic"
        else:
            mode = "bicubic"

        logger.debug(f"Using interpolation mode: {mode}")

        # Upscale using F.interpolate
        upscaled = F.interpolate(
            frame_chw,
            size=(target_height, target_width),
            mode=mode,
            align_corners=False if mode in ["bilinear", "bicubic"] else None,
            antialias=True,
        )
        logger.debug(f"After interpolation: {upscaled.shape}")

        # Convert back to [1, H, W, C] and clamp to [0, 255]
        upscaled = upscaled.permute(0, 2, 3, 1)
        upscaled = torch.clamp(upscaled, 0, 255).byte()
        logger.debug(
            f"Final interpolated frame: {upscaled.shape}, dtype={upscaled.dtype}"
        )

        return upscaled

    def _upscale_realesrgan(
        self, frame: torch.Tensor, target_height: int, target_width: int
    ) -> torch.Tensor:
        """Upscale using Real-ESRGAN."""
        if self.realesrgan_model is None:
            logger.warning("Real-ESRGAN model not loaded, falling back to bicubic")
            return self._upscale_interpolation(frame, target_height, target_width)

        # Convert from [1, H, W, C] to PIL Image
        # Real-ESRGAN expects PIL Image
        import numpy as np
        from PIL import Image

        frame_np = frame.squeeze(0).cpu().numpy().astype("uint8")
        frame_pil = Image.fromarray(frame_np)

        # Upscale using Real-ESRGAN
        # Note: Real-ESRGAN has fixed scale factors (2x, 4x), so we may need multiple passes
        upscaled_pil = self.realesrgan_model.predict(frame_pil)

        # Convert PIL Image back to numpy array
        upscaled_np = np.array(upscaled_pil).astype("uint8")

        # If we need a different size than what Real-ESRGAN produced, resize
        if (
            upscaled_np.shape[0] != target_height
            or upscaled_np.shape[1] != target_width
        ):
            upscaled_tensor = (
                torch.from_numpy(upscaled_np).permute(2, 0, 1).unsqueeze(0)
            )
            upscaled_tensor = F.interpolate(
                upscaled_tensor,
                size=(target_height, target_width),
                mode="bicubic",
                align_corners=False,
                antialias=True,
            )
            upscaled_np = (
                upscaled_tensor.squeeze(0)
                .permute(1, 2, 0)
                .cpu()
                .numpy()
                .astype("uint8")
            )

        # Convert back to [1, H, W, C] tensor
        upscaled = torch.from_numpy(upscaled_np).unsqueeze(0)

        # Move to original device (will be handled by caller)
        return upscaled
