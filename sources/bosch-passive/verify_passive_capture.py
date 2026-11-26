"""Verify the full approved-RAM Chery d1/d4 passive capture image."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from build import AGE, CAN_ID, DEFER, PASSIVE_DEFER_UNIT, PHASE, STALE_CALLS, build, digest
from verify import SPEED_PHYS, payload
import verify_bench_profile as bench
import verify_rx_timestamp as receiver


PREVIOUS_SHA = '5292fdd41cfb5e2055742ab28d85d5e109f509f840fb82c855ee0bd1b82d8875'
OPTIONS = dict(model_fields=True, ordinary_model_field=True, compact=True,
               rx_timestamp=True, rb_native_permit=True)


def verify_capture_words(image, symbols):
    from audit_machine import Machine
    machine = Machine(image)
    entry = symbols['chery_sample_start']
    stop = symbols['chery_sample_done']
    for pair in range(65536):
        b1, b4 = pair & 255, pair >> 8
        machine.poke(0xEF1E, (b1 << 8) | (b4 ^ 255))
        machine.poke(0xEF22, ((b1 ^ 255) << 8) | b4)
        before = len(machine.writes)
        machine.run(entry, stop=stop)
        assert machine.writes[before:] == [(DEFER, pair)]
    return 65536


def verify_coexistence(baseline, old_symbols, image, symbols):
    from torque_patch import command
    cases = []
    for delay in (0, 1, 3):
        old_rx = receiver.Receiver(baseline, old_symbols)
        new_rx = receiver.Receiver(image, symbols)
        for rx in (old_rx, new_rx):
            m = rx.machine
            m.transfer_delay = delay
            m.poke(0xFD18, 0x40)
            m.poke(0xFD1A, 0)
            m.poke(0xF7C4, 8000)
            m.poke(0xF0382, 180, 1)
            m.poke(0xF325A, 1)
            m.poke(0xF32B0, 1)
            m.poke(0xF3286, 1)
            m.poke(0xF3288, 1)
        for tick in range(1, 361):
            for rx in (old_rx, new_rx):
                m = rx.machine
                if tick % 13 == 0:
                    packet = payload(6000, operand1=tick & 255, operand4=(tick * 3) & 255,
                                     corrupt=tick % 65 == 0)
                    assert m.inject(CAN_ID, packet)
                if tick in (40, 180, 300):
                    assert m.inject(0x7E0, bytes.fromhex('0201000000000000'))
                if tick == 92:
                    assert m.inject(0x7E0, bytes.fromhex('0322f20700000000'))
                if tick in (60, 90, 120):
                    assert m.inject(0x5E8, command(1 if tick == 60 else 2, tick // 30, 32, 20, 1))
                if tick == 150:
                    assert m.inject(0x5E8, command(0, 5, 0, 0, 1))
                rx.step(tick * 125)
            old, new = old_rx.machine, new_rx.machine
            assert old.get(SPEED_PHYS) == new.get(SPEED_PHYS)
            assert old.get(AGE) == new.get(AGE)
            assert old.get(PHASE) == new.get(PHASE) & 255
            assert old.get(DEFER) == new.get(PHASE) >> 8
            if new.get(AGE) == 0:
                assert new.get(DEFER) == 0
            assert old.frames == new.frames
        frames = new_rx.machine.frames
        assert {0x0FA, 0x278, 0x5E9, 0x7E8} <= {record['id'] for record in frames}
        responses = [record['data'] for record in frames if record['id'] == 0x7E8]
        assert any(message.startswith('037f2231') for message in responses), responses
        cases.append({'if1_delay': delay, 'service_calls': 360, 'identical_wire_frames': len(frames),
                      'maximum_model_system_stack': new_rx.machine.max_stack})
    return cases


def verify(engine, s04, image):
    baseline, baseline_manifest, _, _ = build(engine, s04, **OPTIONS)
    exact, manifest, _, _ = build(engine, s04, passive_chery=True, **OPTIONS)
    assert PREVIOUS_SHA == digest(baseline)
    assert image == exact
    assert manifest['checksum_records'] == 51
    from build_can_diag import checks
    assert all(record['valid'] for record in checks(image))
    for name in ('engine_signals_tx', 'speed_selector', 'rb_native_permit', 'rb_native_permit_hook'):
        region = manifest['regions'][name]
        offset = int(region['offset'], 16)
        assert image[offset:offset+region['length']] == baseline[offset:offset+region['length']]
    old_symbols = {name: int(value, 16) for name, value in baseline_manifest['speed_receiver_symbols'].items()}
    symbols = {name: int(value, 16) for name, value in manifest['speed_receiver_symbols'].items()}
    normal_rx = receiver.verify_image(baseline, baseline_manifest)
    passive_rx = receiver.verify_image(image, manifest)
    for key in ('captures', 'rejections', 'recovery', 'speed_expiry_service_calls'):
        assert normal_rx[key] == passive_rx[key]
    with patch.object(bench, 'build', lambda *args, **kwargs: build(*args, passive_chery=True, **kwargs)):
        regression = bench.verify(engine, s04, image, rx_timestamp=True)
    return {'status': 'PASS_OFFLINE_ONLY', 'sha256': manifest['sha256'], 'baseline_sha256': PREVIOUS_SHA,
            'the_same_byte_exact_build': True, 'checksum_records': 51,
            'passive_pair_capture_cases': verify_capture_words(image, symbols),
            'positive_rx_timing_cases': len(passive_rx['captures']),
            'rx_rejection_cases': passive_rx['rejections'], 'rx_recovery_cases': passive_rx['recovery'],
            'rb_native_start_admission_cases': len(regression['start_admission']),
            'rb_native_revocations': len(regression['native_revocation']),
            'startup_stack_paths': len(regression['startup_stack_paths']),
            'coexistence': verify_coexistence(baseline, old_symbols, image, symbols),
            'hardware_tested': False, 'new_diagnostic_services': False,
            'chery_passive_capture': manifest['chery_passive_capture']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('engine', 's04', 'image'):
        parser.add_argument('--' + argument, required=True, type=Path)
    args = parser.parse_args()
    assert __debug__
    print(json.dumps(verify(args.engine, args.s04.read_bytes(), args.image.read_bytes()), indent=2))
