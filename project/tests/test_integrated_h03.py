"""Regression checks for independent H03 sizing runs and builder options."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "targets/lfj8"))
import check_integrated_h03 as integrated
import check_h03_link as link


class IntegratedH03Tests(unittest.TestCase):
    def arguments(self, small=False):
        return argparse.Namespace(small_model=small, base=Path("base.bin"),
                                  gcc=Path("m32r-elf-gcc"), out=Path("output"),
                                  controller=Path("controller.o"), bridge=Path("bridge.o"),
                                  bosch_trace=Path("trace.json"))

    def state(self):
        return {name: getattr(link, name) for name in
                ("TARGET", "H03_ROOTS", "DTC_FILES", "DTC_ROOTS", "CAN_EXTENSION_FILES",
                 "CAN_EXTENSION_ROOTS", "check_split_layout")}

    def test_repeated_expanded_checks_preserve_linker_state(self):
        before = self.state()
        observed = []

        def check(*args):
            observed.append(self.state())
            return {}

        args = self.arguments()
        with patch.object(link, "check", side_effect=check):
            self.assertTrue(integrated.expanded(args)["passed"])
            self.assertTrue(integrated.expanded(args)["passed"])
        self.assertEqual(before, self.state())
        self.assertEqual(observed[0]["H03_ROOTS"], observed[1]["H03_ROOTS"])
        self.assertEqual(observed[0]["CAN_EXTENSION_FILES"], observed[1]["CAN_EXTENSION_FILES"])
        self.assertEqual(args.controller, Path("controller.o"))

    def test_small_failure_does_not_change_next_medium_run(self):
        before = self.state()
        with patch.object(integrated, "rebuild_objects") as rebuild:
            with patch.object(link, "check", side_effect=ValueError("layout rejected")):
                with self.assertRaisesRegex(ValueError, "layout rejected"):
                    integrated.expanded(self.arguments(small=True))
            rebuild.assert_called_once()
            self.assertEqual(rebuild.call_args.args[1], "small")
        self.assertEqual(before, self.state())
        with patch.object(link, "check", return_value={}):
            integrated.expanded(self.arguments())
        self.assertEqual(before, self.state())

    def test_controller_failure_does_not_start_bridge_or_replace_inputs(self):
        args = self.arguments(small=True)
        with patch.object(integrated.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "build")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                integrated.rebuild_objects(args, "small")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(args.controller, Path("controller.o"))
        self.assertEqual(args.bridge, Path("bridge.o"))

    def test_small_builder_uses_both_public_provenance_paths(self):
        args = self.arguments(small=True)
        with patch.object(integrated.subprocess, "run") as run:
            integrated.rebuild_objects(args, "small")
        controller, bridge = [call.args[0] for call in run.call_args_list]
        self.assertEqual(controller[controller.index("--memory-model") + 1], "small")
        self.assertEqual(bridge[bridge.index("--m32r-memory-model") + 1], "small")
        self.assertEqual(bridge[bridge.index("--base-9e1c") + 1], "base.bin")
        self.assertEqual(args.controller, args.out / "controller/rbm_u340e_m32r_be.o")
        self.assertEqual(args.bridge, args.out / "bridge/lfj8_9e1c_m32r.o")

    def test_bridge_rejects_invalid_model_before_invoking_compiler(self):
        spec = importlib.util.spec_from_file_location("test_lfj8_builder", ROOT / "targets/lfj8/build.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with patch.object(builder, "command") as command:
            for architecture, model in (("m32r", "large"), ("sh", "small")):
                with self.subTest(architecture=architecture, model=model):
                    with self.assertRaises(ValueError):
                        builder.build_embedded(Path("compiler"), Path("output"), architecture, "m2",
                                               memory_model=model)
            command.assert_not_called()

    def test_cli_rejects_model_for_non_m32r_builds(self):
        with TemporaryDirectory() as directory:
            cases = (
                (["controller/build_target.py", "sh2", "--cc", "unused-compiler",
                  "--memory-model", "small"], "applies only to m32r"),
                (["targets/lfj8/build.py", "--output", directory, "--zig", "unused-compiler",
                  "--m32r-memory-model", "small"], "requires --m32r-cc"),
            )
            for arguments, message in cases:
                with self.subTest(builder=arguments[0]):
                    result = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(message, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
