"""Video upscaling module with support for multiple upscaling methods."""

import logging
from enum import Enum

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class UpscaleMethod(str, Enum):
    """Upscaling method options."""

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
        if self.method == UpscaleMethod.REAL_ESRGAN:
            self._load_realesrgan()

    def _load_realesrgan(self):
        """Lazy load Real-ESRGAN model."""
        try:
            from realesrgan import RealESRGAN

            # Use RealESRGAN_x4plus model (4x upscaling)
            # For 2x, we can use RealESRGAN_x2plus, but x4plus works for any scale
            self.realesrgan_model = RealESRGAN(self.device, scale=4)
            self.realesrgan_model.load_weights(
                "weights/RealESRGAN_x4plus.pth", download=True
            )
            logger.info("Real-ESRGAN model loaded successfully")
        except ImportError:
            logger.warning(
                "Real-ESRGAN not available. Install with: pip install realesrgan"
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
        if frame.dim() != 4 or frame.shape[0] != 1:
            raise ValueError(f"Expected frame shape [1, H, W, C], got {frame.shape}")

        _, height, width, channels = frame.shape

        # Calculate target dimensions
        if target_height is None or target_width is None:
            target_height = int(height * self.scale_factor)
            target_width = int(width * self.scale_factor)
        else:
            # If both specified, use them directly
            pass

        # If no upscaling needed, return as-is
        if target_height == height and target_width == width:
            return frame

        # Keep frame on its current device (usually GPU for performance)
        # Only move to upscaler device if different and method requires it
        original_device = frame.device
        if self.method == UpscaleMethod.REAL_ESRGAN and frame.device != self.device:
            frame = frame.to(self.device)

        if self.method == UpscaleMethod.REAL_ESRGAN:
            result = self._upscale_realesrgan(frame, target_height, target_width)
        else:
            result = self._upscale_interpolation(frame, target_height, target_width)

        # Ensure result is on the same device as input
        if result.device != original_device:
            result = result.to(original_device)

        return result

    def _upscale_interpolation(
        self, frame: torch.Tensor, target_height: int, target_width: int
    ) -> torch.Tensor:
        """Upscale using PyTorch interpolation methods."""
        # Convert from [1, H, W, C] to [1, C, H, W] for interpolation
        # Keep on same device as input (usually GPU)
        frame_chw = frame.permute(0, 3, 1, 2).float()

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

        # Upscale using F.interpolate
        upscaled = F.interpolate(
            frame_chw,
            size=(target_height, target_width),
            mode=mode,
            align_corners=False if mode in ["bilinear", "bicubic"] else None,
            antialias=True,
        )

        # Convert back to [1, H, W, C] and clamp to [0, 255]
        upscaled = upscaled.permute(0, 2, 3, 1)
        upscaled = torch.clamp(upscaled, 0, 255).byte()

        return upscaled

    def _upscale_realesrgan(
        self, frame: torch.Tensor, target_height: int, target_width: int
    ) -> torch.Tensor:
        """Upscale using Real-ESRGAN."""
        if self.realesrgan_model is None:
            logger.warning("Real-ESRGAN model not loaded, falling back to bicubic")
            return self._upscale_interpolation(frame, target_height, target_width)

        # Real-ESRGAN expects PIL Image or numpy array
        # Convert from [1, H, W, C] to [H, W, C] numpy array
        frame_np = frame.squeeze(0).cpu().numpy().astype("uint8")

        # Upscale using Real-ESRGAN
        # Note: Real-ESRGAN has fixed scale factors (2x, 4x), so we may need multiple passes
        upscaled_np = self.realesrgan_model.predict(frame_np)

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
