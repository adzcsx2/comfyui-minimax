"""Reject timing/geometry mismatches before H3 silently fits a control clip."""

import math


class H3ControlVideoGuard:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 24.0, "forceInput": True}),
                "expected_frames": ("INT", {"default": 124, "min": 5, "max": 362, "step": 17}),
                "width": ("INT", {"default": 1024, "min": 32, "step": 32}),
                "height": ("INT", {"default": 576, "min": 32, "step": 32}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("control_video",)
    FUNCTION = "check"
    CATEGORY = "H3 deployment"

    def check(self, images, fps, expected_frames, width, height):
        if not math.isclose(float(fps), 24.0, rel_tol=0, abs_tol=0.01):
            raise ValueError(
                "Control clip must be 24 fps; changing playback speed is not a timing fix"
            )
        if (
            not 5 <= expected_frames <= 362
            or min(width, height) < 32
            or (expected_frames - 5) % 17
            or width % 32
            or height % 32
        ):
            raise ValueError("Use 17*n+5 frames and dimensions divisible by 32")
        if tuple(images.shape[:3]) != (expected_frames, height, width):
            raise ValueError(
                f"Control clip is {tuple(images.shape[:3])}; expected "
                f"({expected_frames}, {height}, {width}). No automatic stretch/pad is allowed."
            )
        return (images,)


NODE_CLASS_MAPPINGS = {"H3ControlVideoGuard": H3ControlVideoGuard}
NODE_DISPLAY_NAME_MAPPINGS = {"H3ControlVideoGuard": "H3 Control Video Timing / Size Check"}
