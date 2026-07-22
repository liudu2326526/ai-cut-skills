#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import motion_effects_bridge  # noqa: E402
import standalone_renderer  # noqa: E402


class PhoneLayoutTests(unittest.TestCase):
    def test_safe_area_starts_from_phone_source_dimensions(self) -> None:
        material = {
            "layout": "phone",
            "path": "/tmp/phone.png",
            "effective_region": {
                "x": 200,
                "y": 300,
                "width": 320,
                "height": 500,
                "coordinate_space": "source_pixels",
            },
        }
        with patch.object(
            standalone_renderer,
            "media_summary",
            return_value={"width": 720, "height": 1280},
        ):
            result = standalone_renderer.apply_material_safe_area(
                {}, [material], 1080, 1920
            )[0]

        self.assertEqual(
            result["safe_area_decision"],
            "keep_original_size_effective_region_is_clear",
        )
        self.assertNotIn("safe_transform", result)
        self.assertEqual(
            result["effective_region_canvas"],
            {"x": 380.0, "y": 650.0, "width": 320.0, "height": 500.0},
        )

    def test_static_phone_filter_has_no_650x1050_default_scale(self) -> None:
        captured: dict[str, list[str]] = {}

        def capture(command: list[str], *, label: str) -> None:
            self.assertEqual(label, "main-render")
            captured["command"] = command

        material = {
            "layout": "phone",
            "path": Path("/tmp/phone.png"),
            "kind": "image",
            "mapped_start": 0.0,
            "mapped_end": 1.0,
        }
        assets = {
            "font": Path("/tmp/body.ttf"),
            "logo": Path("/tmp/logo.png"),
        }
        with patch.object(standalone_renderer, "run", side_effect=capture):
            standalone_renderer.render_main(
                Path("/tmp/input.mp4"),
                Path("/tmp/captions.ass"),
                Path("/tmp/output.mp4"),
                {"width": 1080, "height": 1920, "fps": 30, "speed": 1.0},
                assets,
                Path("/tmp/fonts"),
                [material],
                1.0,
                show_warning=False,
                logo_mode="full_canvas",
            )

        filter_complex = captured["command"][
            captured["command"].index("-filter_complex") + 1
        ]
        self.assertNotIn("scale=650:1050", filter_complex)
        self.assertIn("[2:v]setsar=1,format=rgba[asset2]", filter_complex)

    def test_motion_phone_fallback_uses_source_dimensions(self) -> None:
        with patch.object(
            motion_effects_bridge,
            "_probe",
            return_value={"width": 720, "height": 1280},
        ):
            layout, source_crop = motion_effects_bridge._layout_for_material(
                {"layout": "phone", "path": "/tmp/phone.png"},
                1080,
                1920,
            )

        self.assertIsNone(source_crop)
        self.assertEqual(layout["width"], 720.0)
        self.assertEqual(layout["height"], 1280.0)
        self.assertEqual(layout["x"], 180.0)
        self.assertEqual(layout["y"], 350.0)


class IconCaptionPlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "width": 1080,
            "height": 1920,
            "font": {
                "caption_style": {
                    "font_size": 70,
                    "scale_x": 100,
                    "scale_y": 100,
                    "outline": 3,
                    "alignment": 2,
                    "margin_left": 72,
                    "margin_right": 72,
                    "position_mode": "center_offset",
                    "x": 0,
                    "y": -500,
                }
            },
        }
        self.material = {
            "layout": "icon",
            "path": "/tmp/icon.png",
            "x": 425,
            "mapped_start": 0.0,
            "mapped_end": 1.0,
            "effective_region": {
                "x": 0,
                "y": 0,
                "width": 243,
                "height": 220,
                "coordinate_space": "source_pixels",
            },
        }

    def prepare(self, material: dict, text: str) -> dict:
        with patch.object(
            standalone_renderer,
            "media_summary",
            return_value={"width": 243, "height": 220},
        ):
            return standalone_renderer.apply_material_safe_area(
                self.config,
                [material],
                1080,
                1920,
                captions=[{"start": 0.0, "end": 1.0, "text": text}],
            )[0]

    def test_icon_defaults_to_above_the_overlapping_caption(self) -> None:
        result = self.prepare(dict(self.material), "开车听 走路听 在家听")

        self.assertEqual(result["source_crop"], [0, 0, 243, 220])
        self.assertEqual(
            result["resolved_placement"],
            {
                "x": 425.0,
                "y": 1078.0,
                "width": 243.0,
                "height": 220.0,
                "source": "caption_relative_default",
            },
        )
        self.assertEqual(result["effective_region_canvas"]["y"], 1078.0)
        self.assertNotIn("safe_transform", result)

    def test_explicit_icon_y_overrides_caption_relative_default(self) -> None:
        material = dict(self.material)
        material["y"] = 800

        result = self.prepare(material, "开车听 走路听 在家听")

        self.assertEqual(result["resolved_placement"]["y"], 800.0)
        self.assertEqual(result["resolved_placement"]["source"], "explicit_y")

    def test_multiline_caption_moves_icon_up(self) -> None:
        single = self.prepare(dict(self.material), "第一行")
        multiline = self.prepare(dict(self.material), "第一行\n第二行")

        self.assertLess(
            multiline["resolved_placement"]["y"],
            single["resolved_placement"]["y"],
        )
        self.assertEqual(multiline["resolved_placement"]["y"], 994.0)

    def test_static_icon_filter_uses_resolved_placement(self) -> None:
        captured: dict[str, list[str]] = {}

        def capture(command: list[str], *, label: str) -> None:
            self.assertEqual(label, "main-render")
            captured["command"] = command

        material = {
            "layout": "icon",
            "path": Path("/tmp/icon.png"),
            "kind": "image",
            "mapped_start": 0.0,
            "mapped_end": 1.0,
            "source_crop": [0, 0, 243, 220],
            "resolved_placement": {
                "x": 425.0,
                "y": 1078.0,
                "width": 243.0,
                "height": 220.0,
                "source": "caption_relative_default",
            },
        }
        assets = {
            "font": Path("/tmp/body.ttf"),
            "logo": Path("/tmp/logo.png"),
        }
        with patch.object(standalone_renderer, "run", side_effect=capture):
            standalone_renderer.render_main(
                Path("/tmp/input.mp4"),
                Path("/tmp/captions.ass"),
                Path("/tmp/output.mp4"),
                self.config | {"fps": 30, "speed": 1.0},
                assets,
                Path("/tmp/fonts"),
                [material],
                1.0,
                show_warning=False,
                logo_mode="full_canvas",
            )

        filter_complex = captured["command"][
            captured["command"].index("-filter_complex") + 1
        ]
        self.assertIn("overlay=x=425:y=1078", filter_complex)
        self.assertNotIn("overlay=x=95:y=720", filter_complex)


class PreserveMaterialSizeTests(unittest.TestCase):
    def test_full_alpha_safe_area_starts_from_source_dimensions(self) -> None:
        material = {
            "layout": "full_alpha",
            "path": "/tmp/full-alpha.png",
            "effective_region": {
                "x": 100,
                "y": 400,
                "width": 200,
                "height": 300,
                "coordinate_space": "source_pixels",
            },
        }
        with patch.object(
            standalone_renderer,
            "media_summary",
            return_value={"width": 720, "height": 1280},
        ):
            result = standalone_renderer.apply_material_safe_area(
                {}, [material], 1080, 1920
            )[0]

        self.assertEqual(
            result["safe_area_decision"],
            "keep_original_size_effective_region_is_clear",
        )
        self.assertNotIn("safe_transform", result)
        self.assertEqual(
            result["effective_region_canvas"],
            {"x": 100.0, "y": 400.0, "width": 200.0, "height": 300.0},
        )

    def test_cta_icon_safe_area_starts_from_source_dimensions(self) -> None:
        material = {
            "layout": "cta_icon",
            "path": "/tmp/cta.png",
            "effective_region": {
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 100,
                "coordinate_space": "source_pixels",
            },
        }
        with patch.object(
            standalone_renderer,
            "media_summary",
            return_value={"width": 200, "height": 100},
        ):
            result = standalone_renderer.apply_material_safe_area(
                {}, [material], 1080, 1920
            )[0]

        self.assertEqual(
            result["effective_region_canvas"],
            {"x": 440.0, "y": 650.0, "width": 200.0, "height": 100.0},
        )
        self.assertNotIn("safe_transform", result)

    def test_static_full_alpha_and_cta_icon_have_no_default_scale(self) -> None:
        captured: dict[str, list[str]] = {}

        def capture(command: list[str], *, label: str) -> None:
            self.assertEqual(label, "main-render")
            captured["command"] = command

        materials = [
            {
                "layout": "full_alpha",
                "path": Path("/tmp/full-alpha.png"),
                "kind": "image",
                "mapped_start": 0.0,
                "mapped_end": 1.0,
            },
            {
                "layout": "cta_icon",
                "path": Path("/tmp/cta.png"),
                "kind": "image",
                "mapped_start": 1.0,
                "mapped_end": 2.0,
            },
        ]
        assets = {
            "font": Path("/tmp/body.ttf"),
            "logo": Path("/tmp/logo.png"),
        }
        with patch.object(standalone_renderer, "run", side_effect=capture):
            standalone_renderer.render_main(
                Path("/tmp/input.mp4"),
                Path("/tmp/captions.ass"),
                Path("/tmp/output.mp4"),
                {"width": 1080, "height": 1920, "fps": 30, "speed": 1.0},
                assets,
                Path("/tmp/fonts"),
                materials,
                2.0,
                show_warning=False,
                logo_mode="full_canvas",
            )

        filter_complex = captured["command"][captured["command"].index("-filter_complex") + 1]
        self.assertNotIn("[2:v]scale=1080:1920", filter_complex)
        self.assertNotIn("[3:v]scale=300:300", filter_complex)
        self.assertIn("[2:v]setsar=1,format=rgba[asset2]", filter_complex)
        self.assertIn("[3:v]setsar=1,format=rgba[asset3]", filter_complex)

    def test_motion_full_alpha_and_cta_icon_fallbacks_use_source_dimensions(self) -> None:
        sizes = {
            Path("/tmp/full-alpha.png"): {"width": 720, "height": 1280},
            Path("/tmp/cta.png"): {"width": 200, "height": 100},
        }
        with patch.object(
            motion_effects_bridge,
            "_probe",
            side_effect=lambda path: sizes[Path(path)],
        ):
            full_layout, full_crop = motion_effects_bridge._layout_for_material(
                {"layout": "full_alpha", "path": "/tmp/full-alpha.png"},
                1080,
                1920,
            )
            cta_layout, cta_crop = motion_effects_bridge._layout_for_material(
                {"layout": "cta_icon", "path": "/tmp/cta.png"},
                1080,
                1920,
            )

        self.assertIsNone(full_crop)
        self.assertEqual((full_layout["width"], full_layout["height"]), (720.0, 1280.0))
        self.assertEqual((full_layout["x"], full_layout["y"]), (0.0, 0.0))
        self.assertIsNone(cta_crop)
        self.assertEqual((cta_layout["width"], cta_layout["height"]), (200.0, 100.0))
        self.assertEqual((cta_layout["x"], cta_layout["y"]), (440.0, 650.0))

    def test_motion_only_crops_effective_region_for_icon_layout(self) -> None:
        region = {
            "x": 100,
            "y": 200,
            "width": 220,
            "height": 300,
            "coordinate_space": "source_pixels",
        }
        effective_canvas = {"x": 280, "y": 550, "width": 220, "height": 300}
        with patch.object(
            motion_effects_bridge,
            "_probe",
            return_value={"width": 720, "height": 1280},
        ):
            for layout in ("full_alpha", "phone", "cta_icon"):
                with self.subTest(layout=layout):
                    resolved, source_crop = motion_effects_bridge._layout_for_material(
                        {
                            "layout": layout,
                            "path": f"/tmp/{layout}.png",
                            "effective_region": region,
                            "effective_region_canvas": effective_canvas,
                        },
                        1080,
                        1920,
                    )
                    self.assertIsNone(source_crop)
                    self.assertEqual(
                        (resolved["width"], resolved["height"]),
                        (720.0, 1280.0),
                    )

            icon_layout, icon_crop = motion_effects_bridge._layout_for_material(
                {
                    "layout": "icon",
                    "path": "/tmp/icon.png",
                    "effective_region": region,
                    "effective_region_canvas": effective_canvas,
                },
                1080,
                1920,
            )

        self.assertEqual(icon_crop, [100, 200, 220, 300])
        self.assertEqual(
            (icon_layout["width"], icon_layout["height"]),
            (220.0, 300.0),
        )
        self.assertEqual((icon_layout["x"], icon_layout["y"]), (280.0, 550.0))


class MotionEffectsIntegrationTests(unittest.TestCase):
    def test_plan_rejects_catalog_without_a_valid_default_preset(self) -> None:
        effect = {
            "type": "dynamic_shrink",
            "presets": ["reference_first_v1"],
            "defaultPreset": "reference_first_v2",
            "defaultDuration": 10 / 30,
            "defaultSamples": 72,
        }
        inspection = {
            "mode": "auto",
            "installed": True,
            "ready": True,
            "skill_root": "/tmp/video-motion-effects",
            "cli": "/tmp/video-motion-effects/render.mjs",
            "node": "/usr/bin/node",
            "chrome": "/tmp/chrome",
            "effects": [effect],
            "missing": [],
            "error": None,
            "policy": motion_effects_bridge.resolve_motion_policy({}),
        }
        material = {
            "name": "benefit",
            "path": Path("/tmp/material.png"),
            "kind": "image",
            "layout": "phone",
            "mapped_start": 0.0,
            "mapped_end": 2.0,
        }
        with (
            patch.object(motion_effects_bridge, "inspect_motion_skill", return_value=inspection),
            patch.object(
                motion_effects_bridge,
                "_layout_for_material",
                return_value=({"width": 100.0, "height": 200.0, "x": 0.0, "y": 0.0}, None),
            ),
        ):
            with self.assertRaisesRegex(
                motion_effects_bridge.MotionEffectsError,
                "valid defaultPreset",
            ):
                motion_effects_bridge.plan_motion_effects(
                    {},
                    [material],
                    timeline_path=Path("/tmp/timeline.json"),
                    output_path=Path("/tmp/output.mp4"),
                    canvas_width=1080,
                    canvas_height=1920,
                    fps=30,
                )

    def test_plan_uses_catalog_default_preset_duration_and_samples(self) -> None:
        effect = {
            "type": "dynamic_shrink",
            "presets": ["reference_first_v2", "reference_first_v1"],
            "defaultPreset": "reference_first_v2",
            "defaultDuration": 10 / 30,
            "defaultSamples": 72,
        }
        inspection = {
            "mode": "auto",
            "installed": True,
            "ready": True,
            "skill_root": "/tmp/video-motion-effects",
            "cli": "/tmp/video-motion-effects/render.mjs",
            "node": "/usr/bin/node",
            "chrome": "/tmp/chrome",
            "effects": [effect],
            "missing": [],
            "error": None,
            "policy": motion_effects_bridge.resolve_motion_policy({}),
        }
        material = {
            "name": "benefit",
            "path": Path("/tmp/material.png"),
            "kind": "image",
            "layout": "phone",
            "mapped_start": 0.0,
            "mapped_end": 2.0,
        }
        with (
            patch.object(motion_effects_bridge, "inspect_motion_skill", return_value=inspection),
            patch.object(
                motion_effects_bridge,
                "_layout_for_material",
                return_value=({"width": 100.0, "height": 200.0, "x": 0.0, "y": 0.0}, None),
            ),
        ):
            plan = motion_effects_bridge.plan_motion_effects(
                {},
                [material],
                timeline_path=Path("/tmp/timeline.json"),
                output_path=Path("/tmp/output.mp4"),
                canvas_width=1080,
                canvas_height=1920,
                fps=30,
            )

        event = plan["planned"][0]
        self.assertEqual(event["preset"], "reference_first_v2")
        self.assertAlmostEqual(event["effect_duration"], 10 / 30)
        self.assertEqual(event["samples"], 72)

    def test_page_curl_uses_its_catalog_default_duration(self) -> None:
        effect = {
            "type": "page_curl",
            "presets": ["webgl_page_curl_v1"],
            "defaultPreset": "webgl_page_curl_v1",
            "defaultDuration": 26 / 30,
            "defaultBackTextureStrength": 0.92,
        }
        inspection = {
            "mode": "auto",
            "installed": True,
            "ready": True,
            "skill_root": "/tmp/video-motion-effects",
            "cli": "/tmp/video-motion-effects/render.mjs",
            "node": "/usr/bin/node",
            "chrome": "/tmp/chrome",
            "effects": [effect],
            "missing": [],
            "error": None,
            "policy": motion_effects_bridge.resolve_motion_policy({}),
        }
        material = {
            "name": "benefit",
            "path": Path("/tmp/material.png"),
            "kind": "image",
            "layout": "phone",
            "mapped_start": 0.0,
            "mapped_end": 2.0,
        }
        with (
            patch.object(motion_effects_bridge, "inspect_motion_skill", return_value=inspection),
            patch.object(
                motion_effects_bridge,
                "_layout_for_material",
                return_value=({"width": 100.0, "height": 200.0, "x": 0.0, "y": 0.0}, None),
            ),
        ):
            plan = motion_effects_bridge.plan_motion_effects(
                {},
                [material],
                timeline_path=Path("/tmp/timeline.json"),
                output_path=Path("/tmp/output.mp4"),
                canvas_width=1080,
                canvas_height=1920,
                fps=30,
            )

        self.assertAlmostEqual(plan["planned"][0]["effect_duration"], 26 / 30)
        self.assertIsNone(plan["planned"][0]["samples"])

    def test_motion_readiness_requires_vysmo_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video-motion-effects"
            project = root / "scripts" / "remotion"
            (project / "render.mjs").parent.mkdir(parents=True)
            (project / "render.mjs").touch()
            for relative in (
                "node_modules/remotion/package.json",
                "node_modules/@remotion/renderer/package.json",
                "node_modules/@remotion/bundler/package.json",
            ):
                dependency = project / relative
                dependency.parent.mkdir(parents=True, exist_ok=True)
                dependency.touch()
            process = SimpleNamespace(
                returncode=0,
                stdout='{"effects":[{"type":"dynamic_shrink"}]}',
                stderr="",
            )
            with (
                patch.object(motion_effects_bridge, "_skill_root", return_value=root),
                patch.object(motion_effects_bridge, "_chrome_path", return_value="/tmp/chrome"),
                patch.object(motion_effects_bridge.shutil, "which", return_value="/usr/bin/node"),
                patch.object(motion_effects_bridge.subprocess, "run", return_value=process),
            ):
                inspection = motion_effects_bridge.inspect_motion_skill({})

        self.assertFalse(inspection["ready"])
        self.assertIn(
            "scripts/remotion/node_modules/@vysmo/transitions/package.json",
            inspection["missing"],
        )


if __name__ == "__main__":
    unittest.main()
