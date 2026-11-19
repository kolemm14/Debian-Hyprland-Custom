import unittest
from mpvpaper_engine.media_optimizer import (
    VideoOptimizationConfig,
    ImageOptimizationConfig,
    MediaMetadata,
    estimate_video_optimization,
    estimate_image_optimization,
    build_ffmpeg_video_command,
    OptimizationError,
    DEFAULT_INITIAL_RESOLUTION,
    DEFAULT_INITIAL_MAX_MB,
)


class TestMediaOptimizer(unittest.TestCase):
    def test_default_custom_profile_initial_values(self):
        v_cfg = VideoOptimizationConfig()
        self.assertEqual(v_cfg.resolution, "720p")
        self.assertEqual(v_cfg.target_max_mb, 150.0)
        self.assertTrue(v_cfg.preserve_original)

        i_cfg = ImageOptimizationConfig()
        self.assertEqual(i_cfg.resolution, "720p")
        self.assertEqual(i_cfg.target_max_mb, 150.0)
        self.assertTrue(i_cfg.preserve_original)

    def test_never_overwrite_original(self):
        with self.assertRaises(OptimizationError):
            VideoOptimizationConfig(preserve_original=False)

        with self.assertRaises(OptimizationError):
            ImageOptimizationConfig(preserve_original=False)

        with self.assertRaises(OptimizationError):
            build_ffmpeg_video_command("/tmp/sample.mp4", "/tmp/sample.mp4", VideoOptimizationConfig())

    def test_estimate_video(self):
        meta = MediaMetadata(
            path="/tmp/test.mp4",
            media_type="video",
            width=3840,
            height=2160,
            size_bytes=500 * 1024 * 1024,  # 500 MB
            duration_seconds=60.0,
            fps=60.0,
            codec="h264",
        )
        cfg = VideoOptimizationConfig(resolution="720p", fps="30", compression="medium", target_max_mb=150.0)
        est = estimate_video_optimization(meta, cfg)
        self.assertEqual(est["target_resolution"], "1280x720")
        self.assertEqual(est["target_fps"], 30)
        self.assertTrue(est["requires_lossy_confirmation"])
        self.assertFalse(est["will_overwrite_original"])
        self.assertLessEqual(est["estimated_size_mb"], 150.0)

    def test_estimate_image(self):
        meta = MediaMetadata(
            path="/tmp/test.png",
            media_type="image",
            width=3840,
            height=2160,
            size_bytes=20 * 1024 * 1024,  # 20 MB
        )
        cfg = ImageOptimizationConfig(resolution="1080p", format="webp", compression="medium")
        est = estimate_image_optimization(meta, cfg)
        self.assertEqual(est["target_resolution"], "1920x1080")
        self.assertEqual(est["target_format"], "webp")
        self.assertTrue(est["requires_lossy_confirmation"])
        self.assertFalse(est["will_overwrite_original"])

    def test_build_ffmpeg_command(self):
        cfg = VideoOptimizationConfig(resolution="720p", fps="30", codec="hevc", compression="strong")
        cmd = build_ffmpeg_video_command("/tmp/input.mp4", "/tmp/output.mp4", cfg)
        self.assertIn("ffmpeg", cmd[0])
        self.assertIn("-c:v", cmd)
        self.assertIn("libx265", cmd)
        self.assertIn("scale=1280:720", " ".join(cmd))
        self.assertIn("fps=30", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
