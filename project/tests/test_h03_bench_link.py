"""Test opt-in scoping and refusal paths; these tests do not qualify an image."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import link_h03_bench_candidate as link


class BenchLinkTests(unittest.TestCase):
    def profile(self, directory):
        source = directory / link.bench.SYMBOL_SOURCE
        source.write_text(link.bench.absolute_symbol_source(link.bench.stack_symbols()),
                          encoding="ascii", newline="\n")
        header = directory / "h03_bench_memory_profile.h"
        header.write_text("/* Context scope test only. */\n", encoding="ascii")
        return {"symbols": link.bench.stack_symbols(), "symbol_source": source, "header": header}

    def test_flags_apply_only_to_exact_compiler_consumers_and_compile_phases(self):
        calls = []
        process = SimpleNamespace(run=lambda command, **kwargs: calls.append((command, kwargs)))
        compiler = Path(sys.executable).resolve()
        with TemporaryDirectory() as temporary:
            profile = self.profile(Path(temporary))
            with patch.object(link.layout, "subprocess", process):
                with link.memory_inputs(compiler, profile) as applied:
                    for name in link.bench.NATIVE_SOURCES:
                        source = link.TARGET / name
                        for phase in ("-E", "-c"):
                            link.layout.subprocess.run([compiler, phase, source, "-o", "unit.o"], check=True)
                            argv, kwargs = calls[-1]
                            for value in link.bench.native_compile_flags(profile, source):
                                self.assertIn(value, argv)
                            self.assertEqual(kwargs, {"check": True})
                    self.assertTrue(all(value == {"preprocess": 1, "compile": 1}
                                        for value in applied.values()))
                    unchanged = [
                        [compiler, "-c", Path(temporary) / link.bench.MODULE],
                        [compiler, "-c", link.TARGET / "lfj8_h03_torque.c"],
                        [compiler, "-nostdlib", "-r", link.TARGET / link.bench.MODULE],
                        [Path(temporary) / "other-gcc", "-c", link.TARGET / link.bench.MODULE],
                    ]
                    for command in unchanged:
                        link.layout.subprocess.run(command)
                        self.assertEqual(calls[-1][0], list(map(str, command)))
                self.assertIs(link.layout.subprocess, process)
        self.assertIs(subprocess.run, link.subprocess.run)

    def test_generated_exception_delegates_all_ordinary_paths_to_original_policy(self):
        with TemporaryDirectory() as temporary:
            profile = self.profile(Path(temporary))
            original = link.layout.extra_binding_sources
            native = link.TARGET / link.bench.MODULE
            with link.memory_inputs(sys.executable, profile):
                self.assertEqual(link.layout.extra_binding_sources([native, profile["symbol_source"]]),
                                 [native.resolve(), profile["symbol_source"].resolve()])
                with self.assertRaisesRegex(ValueError, "native H03 binding source"):
                    link.layout.extra_binding_sources([Path(temporary) / "foreign.c", profile["symbol_source"]])
                for sources in ([], [native], [profile["symbol_source"], profile["symbol_source"]]):
                    with self.assertRaisesRegex(ValueError, "exactly once"):
                        link.layout.extra_binding_sources(sources)
                profile["symbol_source"].write_text(".globl unexpected\n", encoding="ascii")
                with self.assertRaisesRegex(ValueError, "unchanged"):
                    link.layout.extra_binding_sources([profile["symbol_source"]])
            self.assertIs(link.layout.extra_binding_sources, original)

    def test_restores_both_references_after_linker_exception(self):
        original_process = link.layout.subprocess
        original_sources = link.layout.extra_binding_sources
        with TemporaryDirectory() as temporary:
            profile = self.profile(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "linker failed"):
                with link.memory_inputs(sys.executable, profile):
                    raise RuntimeError("linker failed")
        self.assertIs(link.layout.subprocess, original_process)
        self.assertIs(link.layout.extra_binding_sources, original_sources)

    def test_refuses_changed_abs_values_or_source_before_installing_hooks(self):
        original_process = link.layout.subprocess
        original_sources = link.layout.extra_binding_sources
        with TemporaryDirectory() as temporary:
            profile = self.profile(Path(temporary))
            changed = deepcopy(profile)
            changed["symbols"]["rbm_h03_ram_spi_reserve"] = 0
            for value in (changed, {**profile, "symbol_source": profile["header"]}):
                with self.assertRaisesRegex(ValueError, "canonical generated"):
                    with link.memory_inputs(sys.executable, value):
                        self.fail("Invalid symbols entered the scoped context")
            self.assertIs(link.layout.subprocess, original_process)
            self.assertIs(link.layout.extra_binding_sources, original_sources)

    def test_refuses_simulator_header_and_existing_output_without_building(self):
        with TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            profile = directory / "COMPOSITION_SIMULATOR_ONLY.h"
            profile.touch()
            args = argparse.Namespace(out=directory / "new", application_profile=profile)
            with patch.object(link.layout, "build") as build:
                with self.assertRaisesRegex(ValueError, "actual native application header"):
                    link.link_candidate(args)
                self.assertFalse(args.out.exists())
                args.out = directory
                with self.assertRaisesRegex(ValueError, "new output directory"):
                    link.link_candidate(args)
                build.assert_not_called()

    def test_failed_common_link_retains_actual_unresolved_report_without_compose_inputs(self):
        original_process = link.layout.subprocess
        original_sources = link.layout.extra_binding_sources
        with TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            input_path = directory / "input"
            input_path.write_bytes(b"test input; no ROM identity or ELF is claimed")
            args = argparse.Namespace(out=directory / "attempt", application_profile=input_path,
                gcc=sys.executable, base=input_path, storage_report=input_path,
                controller=input_path, bridge=input_path, binding_source=[], memory_model="medium")
            storage = {"blocks": {"control": {"end_exclusive": 0x806FAC}}}

            def prepare(image, inventory, pointer, stage):
                self.assertEqual(pointer, storage["blocks"]["control"]["end_exclusive"])
                return self.profile(stage)

            def fail(options):
                self.assertEqual(options.profile, "padding-candidate")
                self.assertTrue(all(getattr(options, name) for name in (
                    "with_bindings", "with_dtc_rx", "with_dma4_guard", "with_service_guard",
                    "with_ram_owner", "with_application_entries", "with_can_service", "with_resident_constants")))
                report = {"status": "FAIL_BINDINGS", "unresolved_symbols": ["missing_native_provider"],
                          "flash_payload_bytes": 123, "new_static_ram_bytes": 4}
                link.save(options.out / "layout.json", report)
                raise ValueError("Production bindings unresolved: missing_native_provider")

            with patch.object(link.layout, "read_storage_report", return_value=storage), \
                    patch.object(link.bench, "prepare", side_effect=prepare), \
                    patch.object(link.layout, "build", side_effect=fail):
                with self.assertRaisesRegex(ValueError, "missing_native_provider"):
                    link.link_candidate(args)
            state = json.loads((args.out / "link-result.json").read_text(encoding="utf-8"))
            self.assertEqual(state["common_layout_status"], "FAIL_BINDINGS")
            self.assertEqual(state["unresolved_symbols"], ["missing_native_provider"])
            self.assertFalse(state["bench_pair_ready"])
            self.assertIsNone(state["flashable_image"])
            self.assertNotIn("compose_inputs", state)
            self.assertFalse(list(args.out.rglob("*.bin")))
        self.assertIs(link.layout.subprocess, original_process)
        self.assertIs(link.layout.extra_binding_sources, original_sources)


if __name__ == "__main__":
    unittest.main()
