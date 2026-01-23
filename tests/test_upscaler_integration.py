"""Test upscaling integration with FrameProcessor."""

import logging
from unittest.mock import MagicMock

import torch

from scope.server.frame_processor import FrameProcessor

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_frame_processor_upscaling():
    """Test that FrameProcessor correctly applies upscaling."""
    # Create a mock pipeline manager
    pipeline_manager = MagicMock()
    pipeline_manager.get_status_info.return_value = {
        "load_params": {"width": 512, "height": 512}
    }

    # Create FrameProcessor
    frame_processor = FrameProcessor(
        pipeline_manager=pipeline_manager,
        initial_parameters={"pipeline_ids": ["test_pipeline"]},
    )

    # Mock pipeline processor to simulate frame output
    mock_processor = MagicMock()
    mock_processor.output_queue = MagicMock()
    mock_processor.get_fps.return_value = 30.0

    # Create a test frame: [1, H, W, C] format
    test_frame = torch.randint(0, 256, (1, 256, 256, 3), dtype=torch.uint8)

    # Mock the output queue to return our test frame
    def mock_get_nowait():
        return test_frame

    mock_processor.output_queue.get_nowait = mock_get_nowait
    mock_processor.output_queue.__bool__ = lambda x: True

    frame_processor.pipeline_processors = [mock_processor]
    frame_processor.running = True

    # Enable upscaling
    print("\n" + "=" * 80)
    print("Testing upscaling integration")
    print("=" * 80)

    upscale_config = {
        "enabled": True,
        "method": "bicubic",
        "scale_factor": 2.0,
    }

    print(f"\n1. Enabling upscaling with config: {upscale_config}")
    frame_processor.update_parameters({"upscale": upscale_config})

    print(f"   Upscale enabled: {frame_processor.upscale_enabled}")
    print(f"   Upscaler exists: {frame_processor.upscaler is not None}")
    if frame_processor.upscaler:
        print(f"   Upscaler method: {frame_processor.upscaler.method}")
        print(f"   Upscaler scale: {frame_processor.upscaler.scale_factor}")

    # Get a frame (should be upscaled)
    print(f"\n2. Getting frame (input shape: {test_frame.shape})")
    output_frame = frame_processor.get()

    if output_frame is not None:
        print(f"   Output frame shape: {output_frame.shape}")
        print("   Expected upscaled shape: (512, 512, 3)")
        if output_frame.shape == (512, 512, 3):
            print("   ✓ Frame was successfully upscaled!")
        else:
            print(
                f"   ✗ Frame was NOT upscaled (expected 512x512, got {output_frame.shape})"
            )
    else:
        print("   ✗ No frame returned!")

    # Test disabling upscaling
    print("\n3. Disabling upscaling")
    frame_processor.update_parameters({"upscale": {"enabled": False}})
    print(f"   Upscale enabled: {frame_processor.upscale_enabled}")
    print(f"   Upscaler exists: {frame_processor.upscaler is not None}")

    # Get a frame (should NOT be upscaled)
    print("\n4. Getting frame after disabling upscaling")
    output_frame = frame_processor.get()
    if output_frame is not None:
        print(f"   Output frame shape: {output_frame.shape}")
        if output_frame.shape == (256, 256, 3):
            print("   ✓ Frame is back to original size!")
        else:
            print(f"   ✗ Unexpected shape: {output_frame.shape}")

    print("\n" + "=" * 80)
    print("Integration test complete")
    print("=" * 80)


def main():
    """Run integration test."""
    try:
        test_frame_processor_upscaling()
        print("\n✓ All integration tests passed!")
        return 0
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
