import unittest

from targets.bosch.compact_branches import compact_local_branches


class Section:
    def __init__(self, instructions, *, origin=0x066000, labels=None):
        self.origin = origin
        self.labels = labels or {}
        self.fix = []
        self.data = bytearray()
        self.rows = []
        for encoding, description in instructions:
            raw = bytes.fromhex(encoding)
            self.rows.append((origin + len(self.data), len(raw), description))
            self.data.extend(raw)

    def finish(self):
        return bytes(self.data)


class BoschCompactBranchesTests(unittest.TestCase):
    def test_keeps_external_same_segment_jump_after_shrinking_local_jump(self):
        # Cover targets before the section, just after it, and further away.
        for target in ("0062", "0a60", "fe5f"):
            with self.subTest(target=target):
                section = Section([
                    ("ea200860", "JMPA CC_2,tail"),
                    ("ea30" + target, "JMPA CC_3,external"),
                    ("cc00", "NOP"),
                ], labels={"tail": 0x066008})
                actual = compact_local_branches(section, section.finish())
                self.assertEqual(actual, bytes.fromhex("2d02ea30" + target + "cc00"))
                self.assertEqual(section.rows[1], (0x066002, 4, "JMPA CC_3,external"))
                self.assertEqual(section.labels["tail"], 0x066006)

    def test_moves_explicit_end_label(self):
        section = Section([
            ("ea000660", "JMPA end"),
            ("cc00", "NOP"),
        ], labels={"end": 0x066006})
        self.assertEqual(compact_local_branches(section, section.finish()), bytes.fromhex("0d01cc00"))
        self.assertEqual(section.labels["end"], 0x066004)

    def test_relocates_local_far_call_and_keeps_external_far_jump(self):
        section = Section([
            ("ea000860", "JMPA local"),
            ("da060c60", "CALLS 06h,600Ch"),
            ("fa073456", "JMPS 07h,5634h"),
            ("cc00", "NOP"),
        ])
        self.assertEqual(compact_local_branches(section, section.finish()),
                         bytes.fromhex("0d02da060a60fa073456cc00"))

    def test_rejects_branch_into_middle_of_instruction(self):
        for instruction in ("ea000260", "da060260", "fa060260"):
            with self.subTest(instruction=instruction):
                section = Section([(instruction, "bad target")])
                with self.assertRaisesRegex(ValueError, "instruction boundary"):
                    compact_local_branches(section, section.finish())

    def test_rejects_truncated_absolute_instruction(self):
        for instruction in ("ea00", "da06", "fa06"):
            with self.subTest(instruction=instruction):
                section = Section([(instruction, "truncated")])
                with self.assertRaisesRegex(ValueError, "instruction"):
                    compact_local_branches(section, section.finish())

    def test_rejects_code_crossing_a_segment(self):
        section = Section([("cc00", "NOP"), ("cc00", "NOP")], origin=0x06FFFE)
        with self.assertRaisesRegex(ValueError, "segment"):
            compact_local_branches(section, section.finish())
