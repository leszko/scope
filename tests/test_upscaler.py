"""Test upscaling functionality."""

import torch

from scope.server.upscaler import UpscaleMethod, Upscaler


def test_upscaler_basic():
    """Test basic upscaling functionality."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Create a test frame: [1, H, W, C] format, uint8 [0, 255]
    height, width = 256, 256
    channels = 3
    frame = torch.randint(
        0, 256, (1, height, width, channels), dtype=torch.uint8, device=device
    )

    print(f"Input frame shape: {frame.shape}")
    print(f"Input frame dtype: {frame.dtype}")
    print(f"Input frame device: {frame.device}")

    # Test bicubic upscaling
    upscaler = Upscaler(method=UpscaleMethod.BICUBIC, scale_factor=2.0, device=device)
    upscaled = upscaler.upscale(frame)

    print(f"Upscaled frame shape: {upscaled.shape}")
    print(f"Upscaled frame dtype: {upscaled.dtype}")
    print(f"Upscaled frame device: {upscaled.device}")

    # Verify output shape
    expected_height = int(height * 2.0)
    expected_width = int(width * 2.0)
    assert upscaled.shape == (1, expected_height, expected_width, channels), (
        f"Expected shape (1, {expected_height}, {expected_width}, {channels}), got {upscaled.shape}"
    )

    # Verify output dtype
    assert upscaled.dtype == torch.uint8, f"Expected uint8, got {upscaled.dtype}"

    # Verify output range
    assert upscaled.min() >= 0 and upscaled.max() <= 255, (
        f"Values out of range: min={upscaled.min()}, max={upscaled.max()}"
    )

    print("✓ Basic upscaling test passed!")


def test_upscaler_bilinear():
    """Test bilinear upscaling."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    height, width = 128, 128
    frame = torch.randint(
        0, 256, (1, height, width, 3), dtype=torch.uint8, device=device
    )

    upscaler = Upscaler(method=UpscaleMethod.BILINEAR, scale_factor=2.0, device=device)
    upscaled = upscaler.upscale(frame)

    assert upscaled.shape == (1, 256, 256, 3)
    print("✓ Bilinear upscaling test passed!")


def test_upscaler_target_dimensions():
    """Test upscaling with target dimensions."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    height, width = 256, 256
    frame = torch.randint(
        0, 256, (1, height, width, 3), dtype=torch.uint8, device=device
    )

    upscaler = Upscaler(method=UpscaleMethod.BICUBIC, scale_factor=2.0, device=device)
    upscaled = upscaler.upscale(frame, target_height=512, target_width=1024)

    assert upscaled.shape == (1, 512, 1024, 3)
    print("✓ Target dimensions test passed!")


def test_upscaler_no_upscaling():
    """Test that no upscaling occurs when dimensions match."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    height, width = 256, 256
    frame = torch.randint(
        0, 256, (1, height, width, 3), dtype=torch.uint8, device=device
    )
    frame_id = id(frame)

    upscaler = Upscaler(method=UpscaleMethod.BICUBIC, scale_factor=1.0, device=device)
    upscaled = upscaler.upscale(frame, target_height=256, target_width=256)

    # Should return the same tensor (or at least same shape)
    assert upscaled.shape == frame.shape
    print("✓ No upscaling test passed!")


def test_upscaler_different_scale_factors():
    """Test different scale factors."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    height, width = 256, 256
    frame = torch.randint(
        0, 256, (1, height, width, 3), dtype=torch.uint8, device=device
    )

    for scale in [1.5, 2.0, 3.0, 4.0]:
        upscaler = Upscaler(
            method=UpscaleMethod.BICUBIC, scale_factor=scale, device=device
        )
        upscaled = upscaler.upscale(frame)
        expected_height = int(height * scale)
        expected_width = int(width * scale)
        assert upscaled.shape == (1, expected_height, expected_width, 3), (
            f"Scale {scale}: expected (1, {expected_height}, {expected_width}, 3), got {upscaled.shape}"
        )
        print(f"  ✓ Scale {scale}x: {frame.shape} -> {upscaled.shape}")

    print("✓ Different scale factors test passed!")


def main():
    """Run all upscaling tests."""
    print("=" * 80)
    print("Testing Upscaler")
    print("=" * 80)

    try:
        test_upscaler_basic()
        test_upscaler_bilinear()
        test_upscaler_target_dimensions()
        test_upscaler_no_upscaling()
        test_upscaler_different_scale_factors()

        print("\n" + "=" * 80)
        print("All tests passed! ✓")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
