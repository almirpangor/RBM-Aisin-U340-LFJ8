"""Reject missing production sections, unsafe placement and stale success artifacts."""
from copy import deepcopy
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'targets/lfj8'))
sys.path.insert(0,str(ROOT/'tools'))
import lfj8_h03_layout as layout
import check_h03_image_layout as builder


def section(name='.text.entry',size=12,alignment=4,flags=6,typ=1,address=0,index=1):
    return dict(name=name,size=size,alignment=alignment,flags=flags,type=typ,
                address=address,index=index,data=b'\x11'*size if typ!=8 else b'')


class PlacementTests(unittest.TestCase):
    def test_every_section_preserved_at_aligned_nonoverlapping_address(self):
        sections=[section('.text.a',24,8),section('.text.b',12),section('.rodata',20,4,2)]
        windows=(layout.Window('one',0x100,0x120),layout.Window('two',0x200,0x220))
        result=layout.pack(sections,windows)
        self.assertEqual({r['section'] for r in result},{s['name'] for s in sections})
        self.assertEqual(sum(r['bytes'] for r in result),56)
        end=0
        for r in result:
            self.assertGreaterEqual(r['address'],end)
            self.assertEqual(r['address']%r['alignment'],0)
            end=r['address']+r['bytes']
        self.assertEqual(result,layout.pack(list(reversed(sections)),tuple(reversed(windows))))

    def test_overflow_and_fragmentation_fail_without_truncating(self):
        for windows in [(layout.Window('one',0,8),),
                        (layout.Window('one',0,8),layout.Window('two',16,24))]:
            with self.assertRaises(layout.PlacementError) as caught:
                layout.pack([section(size=12)],windows)
            self.assertFalse(caught.exception.report['accepted_layout'])
            self.assertEqual(caught.exception.report['unplaced_bytes'],12)

    def test_overlapping_duplicate_unaligned_and_out_of_range_windows(self):
        for windows in [(layout.Window('one',0,8),layout.Window('two',4,12)),
                        (layout.Window('one',0,8),layout.Window('one',8,16)),
                        (layout.Window('one',1,8),),(layout.Window('one',0,0x1000004),)]:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                layout.validate_windows(windows)

    def test_erased_candidate_checks_every_byte_and_bounds(self):
        windows=(layout.Window('one',4,12),)
        layout.validate_windows(windows,b'\0'*4+b'\xff'*8)
        for rom in [b'\0'*4+b'\xff'*7,b'\xff'*11+b'\0']:
            with self.assertRaises(ValueError): layout.validate_windows(windows,rom)

    def test_candidate_profiles_never_touch_boot_or_end_marker(self):
        for windows in layout.PROFILES.values():
            layout.validate_windows(windows)
            for w in windows:
                self.assertGreaterEqual(w.start,0x8000)
                self.assertLessEqual(w.end,0x7FFFC)

    def test_initialized_state_tls_duplicate_and_bad_alignment_rejected(self):
        variants=[[section(flags=3)], [section(flags=0x406)],
                  [section(typ=8,flags=2)], [section(),section()], [section(alignment=3)]]
        for sections in variants:
            with self.assertRaises(ValueError): layout.alloc_sections({'sections':sections})
        self.assertEqual(len(layout.alloc_sections({'sections':[section(typ=8,flags=3)]})),1)

    def test_final_link_roots_sections_relocations_and_addresses(self):
        plan=layout.pack([section()],(layout.Window('one',0x100,0x120),))
        elf={'sections':[section('',0,flags=0,index=0),section('.p0000',address=0x100)],
             'symbols':{'entry':{'address':0x100,'section':1,'size':12,'type':2}}}
        layout.verify_linked(elf,plan,['entry'])
        variants=[]
        bad=deepcopy(elf); bad['sections'][1]['address']+=4; variants.append(bad)
        bad=deepcopy(elf); bad['sections'].append(section('.orphan')); variants.append(bad)
        bad=deepcopy(elf); bad['sections'].append(section('.rela',flags=0,typ=9)); variants.append(bad)
        bad=deepcopy(elf); bad['symbols']['entry']['section']=0; variants.append(bad)
        bad=deepcopy(elf); bad['symbols']['entry']['address']=0x120; variants.append(bad)
        bad=deepcopy(elf); bad['symbols']={}; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError): layout.verify_linked(bad,plan,['entry'])

    def test_calibration_symbol_bounds_are_checked(self):
        elf={'sections':[section('',0),section('.rodata',size=8,address=0x100)],
             'symbols':{'cal':{'address':0x104,'section':1,'size':4}}}
        self.assertEqual(layout.symbol_bytes(elf,'cal'),b'\x11'*4)
        for address,size in [(0xFF,4),(0x104,5)]:
            elf['symbols']['cal'].update(address=address,size=size)
            with self.assertRaises(ValueError): layout.symbol_bytes(elf,'cal')

    def test_elf_wrong_machine_endian_truncated_table_and_names_rejected(self):
        header=bytearray(52)
        header[:7]=b'\x7fELF\x01\x02\x01'
        struct.pack_into('>HHI',header,16,1,88,1)
        struct.pack_into('>I',header,32,52)
        struct.pack_into('>HHH',header,46,40,1,0)
        valid=header+struct.pack('>10I',0,3,0,0,92,1,0,0,1,0)+b'\0'
        with TemporaryDirectory() as folder:
            path=Path(folder)/'object.o'
            path.write_bytes(valid)
            self.assertEqual(layout.read_elf(path,1)['symbols'],{})
            variants=[valid[:51],valid[:70],valid[:-1]]
            for offset,value in [(5,1),(19,89),(59,1),(55,2)]:
                bad=bytearray(valid); bad[offset]=value; variants.append(bad)
            for bad in variants:
                path.write_bytes(bad)
                with self.assertRaises(ValueError): layout.read_elf(path,1)

    def test_new_attempt_invalidates_stale_success_but_preserves_inputs(self):
        with TemporaryDirectory() as folder:
            out=Path(folder)
            original=out/'original.bin'; original.write_bytes(b'original')
            for name in ('layout.elf','placement.ld','layout.json','summary.json'):
                (out/name).write_text('stale success')
            builder.invalidate_outputs(out,[original])
            self.assertEqual(list(out.iterdir()),[original])
            protected=out/'layout.elf'; protected.write_bytes(b'input')
            with self.assertRaises(ValueError): builder.invalidate_outputs(out,[protected])
            self.assertEqual(protected.read_bytes(),b'input')

    def test_missing_or_unidentified_ram_inventory_refused(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'storage.json'
            for content in ('{}','{"artifact_kind":"M32R_ABI_storage_address_model","base":{"sha256":"wrong"}}'):
                path.write_text(content)
                with self.assertRaises(ValueError): builder.storage_space(path)

    def test_toyota_release_is_resolved_only_from_a_typed_field(self):
        storage = {
            "blocks": {"control": {"address": 0x100, "end_exclusive": 0x130}},
            "fields": {"control/application": {"offset": 0, "bytes": 8, "alignment": 4}},
        }
        self.assertIsNone(builder.toyota_release_range(storage))
        storage["fields"][builder.TOYOTA_RELEASE_FIELD] = {"offset": 8, "bytes": 16, "alignment": 4}
        self.assertEqual(builder.toyota_release_range(storage), {
            "field": "control/toyota_release", "symbol": "rbm_h03_toyota_release_state",
            "address": 0x108, "end_exclusive": 0x118, "bytes": 16, "alignment": 4,
        })

    def test_toyota_release_rejects_wrong_geometry_or_overlapping_storage(self):
        storage = {
            "blocks": {"control": {"address": 0x100, "end_exclusive": 0x130}},
            "fields": {"control/application": {"offset": 0, "bytes": 8, "alignment": 4}},
        }
        for overrides in ({"bytes": 12}, {"alignment": 2}, {"offset": 9},
                          {"offset": -4}, {"offset": 0x28}, {"offset": 4}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                storage["fields"][builder.TOYOTA_RELEASE_FIELD] = {
                    "offset": 8, "bytes": 16, "alignment": 4, **overrides,
                }
                builder.toyota_release_range(storage)


if __name__=='__main__':
    unittest.main()
