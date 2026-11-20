#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_chery_tx.h"
#include "lfj8_h03_engine_rx.h"
#include "ta2005_chery_inputs.h"

typedef struct {
    uint32_t freshness;
    uint32_t interval;
    uint32_t capture_timer;
    uint32_t capture_timer_read_step;
    uint32_t captured_ticks;
    uint32_t nt_timer;
    uint32_t nt_captured_ticks;
    uint16_t edge_count;
    uint16_t pulse_count;
    uint16_t can_control;
    uint16_t can_status;
    uint16_t formats;
    uint16_t slot_interrupts;
    uint16_t rx_timestamp;
    uint16_t coolant_timestamp;
    uint16_t can_timestamp;
    uint8_t slot_control;
    uint8_t can_mode;
    uint8_t stock_can_state;
    uint8_t last_sid[2];
    uint8_t last_dlc;
    uint8_t last_data[8];
    uint8_t rx_control;
    uint8_t rx_after;
    uint8_t rx_sid[2];
    uint8_t rx_dlc;
    uint8_t rx_data[8];
    uint8_t mask_sid[2];
    uint8_t coolant_control;
    uint8_t coolant_sid[2];
    uint8_t coolant_after;
    uint8_t coolant_dlc;
    uint8_t coolant_data[8];
    uint8_t coolant_arm_fails;
    uint8_t rpm_arrives_during_coolant_poll;
    unsigned lock_count;
    unsigned lock_depth;
    unsigned writes;
    unsigned submissions;
    uint8_t slot_clear_fails;
    uint8_t use_9e1c_vss_map;
} Fixture;

static uint32_t lock(void *context)
{
    Fixture *f = context;
    ++f->lock_count;
    return f->lock_depth++;
}

static void unlock(void *context, uint32_t state)
{
    Fixture *f = context;
    assert(f->lock_depth != 0u && --f->lock_depth == state);
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth != 0u);
    switch (address) {
    case 0x80105Du: return f->slot_control;
    case 0x801018u: return f->can_mode;
    case 0x806AE6u: return f->stock_can_state;
    case 0x801028u:
    case 0x801029u: return f->mask_sid[address - 0x801028u];
    case 0x80105Bu: return f->rx_control;
    case 0x80105Cu:
        if (f->rpm_arrives_during_coolant_poll) {
            assert(f->rx_control == 0x40u);
            f->rx_control = 0x41u;
            f->rpm_arrives_during_coolant_poll = 0u;
        }
        return f->coolant_control;
    case 0x8011C0u:
    case 0x8011C1u: return f->coolant_sid[address - 0x8011C0u];
    case 0x8011C5u: return f->coolant_dlc;
    case 0x8011B0u:
    case 0x8011B1u: return f->rx_sid[address - 0x8011B0u];
    case 0x8011B5u: return f->rx_dlc;
    default:
        if (address >= 0x8011C6u && address <= 0x8011CDu) {
            return f->coolant_data[address - 0x8011C6u];
        }
        assert(address >= 0x8011B6u && address <= 0x8011BDu);
        return f->rx_data[address - 0x8011B6u];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth != 0u);
    switch (address) {
    case 0x801000u: return f->can_control;
    case 0x801002u: return f->can_status;
    case 0x801004u: return f->formats;
    case 0x801008u: return f->can_timestamp;
    case 0x801010u: return f->slot_interrupts;
    case 0x8011BEu: return f->rx_timestamp;
    case 0x8011CEu: return f->coolant_timestamp;
    case 0x8061C4u:
        assert(f->use_9e1c_vss_map == 0u);
        return f->edge_count;
    case 0x8061CCu:
        return f->use_9e1c_vss_map != 0u ? f->edge_count : f->pulse_count;
    case 0x8061D4u:
        assert(f->use_9e1c_vss_map != 0u);
        return f->pulse_count;
    default: assert(0); return 0;
    }
}

static uint32_t read32(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth != 0u);
    switch (address) {
    case 0x8003E0u: {
        const uint32_t now = f->capture_timer;
        f->capture_timer += f->capture_timer_read_step;
        return now;
    }
    case 0x800FE0u: return f->nt_timer;
    case 0x8048BCu: return f->nt_captured_ticks;
    case 0x804EC4u: return f->freshness;
    case 0x8048B8u:
        assert(f->use_9e1c_vss_map != 0u);
        return f->captured_ticks;
    case 0x806164u:
        assert(f->use_9e1c_vss_map == 0u);
        return f->interval;
    case 0x80616Cu:
        assert(f->use_9e1c_vss_map != 0u);
        return f->interval;
    default: assert(0); return 0;
    }
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *f = context;
    assert(f->lock_depth != 0u);
    ++f->writes;
    switch (address) {
    case 0x80105Bu:
        assert(value == 0x4eu || value == 0x40u || value == 0u);
        f->rx_control = value == 0x4eu ? (uint8_t)(f->rx_after | (f->rx_control & 4u)) : value;
        break;
    case 0x80105Cu:
        assert(value == 0x4eu || value == 0x40u || value == 0u);
        f->coolant_control = value == 0x4eu ? (uint8_t)(f->coolant_after | (f->coolant_control & 4u))
                                          : (f->coolant_arm_fails ? 0u : value);
        break;
    case 0x8011B0u:
    case 0x8011B1u:
        f->rx_sid[address - 0x8011B0u] = value;
        break;
    case 0x8011C0u:
    case 0x8011C1u:
        f->coolant_sid[address - 0x8011C0u] = value;
        break;
    case 0x80105Du:
        assert(value == 0u || value == 0x80u);
        f->slot_control = value == 0u && f->slot_clear_fails != 0u ? 2u : value;
        if (value == 0x80u) {
            ++f->submissions;
        }
        break;
    case 0x8011D0u:
    case 0x8011D1u:
        f->last_sid[address - 0x8011D0u] = value;
        break;
    case 0x8011D5u:
        f->last_dlc = value;
        break;
    default:
        assert(address >= 0x8011D6u && address <= 0x8011DDu);
        f->last_data[address - 0x8011D6u] = value;
        break;
    }
}

static void test_can_receive_assignment(void)
{
    Fixture f = {.mask_sid = {0x1fu, 0x3fu}};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 0u));
    f.slot_interrupts = 0x0008u;
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    f.slot_interrupts = 0;
    f.coolant_control = 0x40u;
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    f.coolant_control = 0;
    f.formats = 0x0010u;
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    f.formats = 0;
    f.mask_sid[1] = 0x3eu;
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    f.mask_sid[1] = 0x3fu;
    assert(f.writes == 0u);

    f.coolant_arm_fails = 1u;
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    assert(f.rx_control == 0u && f.coolant_control == 0u);
    f.coolant_arm_fails = 0u;
    assert(lfj8_h03_can0_arm_engine_rx(&io, 1u));
    assert(f.rx_control == 0x40u && f.coolant_control == 0x40u);
    assert(f.rx_sid[0] == 0x03u && f.rx_sid[1] == 0x3au);
    assert(f.coolant_sid[0] == 0x09u && f.coolant_sid[1] == 0x38u);
    assert(!lfj8_h03_can0_arm_engine_rx(&io, 1u));
    assert(f.writes == 14u && f.lock_depth == 0u);
}

static void test_can_receive(void)
{
    Fixture f = {
        .rx_timestamp = 0xFFFEu,
        .rx_control = 0x41u,
        .rx_after = 0x40u,
        .rx_sid = {0x03u, 0x3Au},
        .rx_dlc = 8u,
        .rx_data = {0x12u, 0xC0u, 0xFFu, 0xFFu, 0x00u, 0xFFu, 0x00u, 0x00u},
    };
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    Lfj8CanData8 frame;
    assert(lfj8_can0_receive8(&io, 14u, 1u, &frame) == LFJ8_CAN_RX_WRONG_SLOT);
    assert(lfj8_can0_receive8(&io, 11u, 0u, &frame) == LFJ8_CAN_RX_WRONG_SLOT);
    assert(f.lock_count == 0u && f.writes == 0u);
    f.formats = 0x0010u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_WRONG_SLOT);
    f.formats = 0;
    f.can_status = 0x4000u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_UNAVAILABLE);
    f.can_status = 0;
    assert(f.writes == 0u);

    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_RECEIVED);
    assert(frame.id == 0x0FAu && frame.timestamp == 0xFFFEu);
    assert(memcmp(frame.payload, f.rx_data, sizeof(frame.payload)) == 0);
    Ta2005CheryInputs engine;
    Ta2005CherySnapshot snapshot;
    uint32_t now = frame.timestamp;
    ta2005_chery_inputs_reset(&engine);
    assert(ta2005_chery_inputs_receive(&engine, frame.id, 8u, frame.payload, &now) ==
           TA2005_CHERY_SPEED);
    assert(ta2005_chery_inputs_snapshot(&engine, &now, 100u, &snapshot) == TA2005_CHERY_SPEED);
    assert(snapshot.speed_fad8 == 9600u);

    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_IDLE);
    assert(f.writes == 1u);
    f.rx_control = 0x43u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_RETRY);
    assert(f.writes == 1u);
    f.rx_control = 0x41u;
    f.rx_after = 0x41u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_RETRY);
    assert(frame.id == 0u && frame.timestamp == 0u);
    f.rx_after = 0x40u;
    f.rx_dlc = 7u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_BAD_LENGTH);
    f.rx_control = 0x45u;
    f.rx_dlc = 8u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_LOST);
    assert(frame.id == 0u && frame.timestamp == 0u && f.writes == 4u && f.lock_depth == 0u);
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_IDLE);
    f.rx_control = 0x41u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_RECEIVED);

    f.rx_control = 0x41u;
    f.rx_sid[0] = 0x09u;
    f.rx_sid[1] = 0x38u;
    f.rx_data[0] = 0xB4u;
    f.rx_timestamp = 0u;
    assert(lfj8_can0_receive8(&io, 11u, 1u, &frame) == LFJ8_CAN_RX_RECEIVED);
    assert(frame.id == 0x278u && frame.timestamp == 0u);
    now = 0x10000u;
    assert(ta2005_chery_inputs_receive(&engine, frame.id, 8u, frame.payload, &now) ==
           TA2005_CHERY_COOLANT);
    assert(ta2005_chery_inputs_snapshot(&engine, &now, 100u, &snapshot) ==
           (TA2005_CHERY_SPEED | TA2005_CHERY_COOLANT));
    assert(snapshot.coolant_f9e9 == 137u);
}

static void test_engine_can_lifecycle(void)
{
    Fixture f = {
        .mask_sid = {0x1fu, 0x3fu},
        .rx_after = 0x40u,
        .coolant_after = 0x40u,
        .rx_dlc = 8u,
        .coolant_dlc = 8u,
        .rx_data = {0x12u, 0xc0u, 0x27u, 0x96u, 0x7fu, 0x11u},
        .coolant_data = {0xb4u},
        .stock_can_state = 4u,
        .can_timestamp = 0xfffau,
    };
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    const unsigned both = TA2005_CHERY_SPEED | TA2005_CHERY_COOLANT;
    const uint32_t start = UINT32_MAX - 30u;
    Lfj8H03EngineRx rx;
    Ta2005CherySnapshot sample;
    assert(!lfj8_h03_engine_rx_init(&rx, 100u, 30001u));
    assert(lfj8_h03_engine_rx_init(&rx, 100u, 1000u));
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start, 1u, &sample) == 0u && f.writes == 0u);
    f.stock_can_state = 6u;
    f.can_status = 0x4000u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start, 1u, &sample) == 0u && f.writes == 0u);
    f.can_status = 0;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start, 1u, &sample) == 0u);
    assert(f.rx_control == 0x40u && f.coolant_control == 0x40u);

    /* The first samples may not use the anchor tick if the clock has yet
     * to move. In particular, the raw model bytes must stay unavailable. */
    f.rx_control = 0x41u;
    f.rx_timestamp = f.can_timestamp;
    f.coolant_control = 0x41u;
    f.coolant_timestamp = f.can_timestamp;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 1u, 1u, &sample) == 0u);
    assert(!rx.clock_running && sample.model.f9e8 == UINT8_MAX);

    f.rx_control = 0x41u;
    f.rx_timestamp = 0xfffeu;
    f.coolant_control = 0x41u;
    f.coolant_timestamp = 1u;
    f.can_timestamp = 4u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 20u, 1u, &sample) == both);
    assert(sample.speed_fad8 == 9600u && sample.coolant_f9e9 == 137u && rx.time_ticks == 10u);
    assert(sample.model.f9d8 == 0x27u && sample.model.f9e8 == 0x96u && sample.model.f914 == 0x11u);

    f.rx_control = 0x45u;
    f.can_timestamp = 10u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 32u, 1u, &sample) == TA2005_CHERY_COOLANT);
    assert(sample.speed_fad8 == UINT16_MAX && f.rx_control == 0x40u);
    assert(sample.model.f9d8 == UINT8_MAX && sample.model.f9e8 == UINT8_MAX && sample.model.f914 == UINT8_MAX);
    f.rx_control = 0x41u;
    f.rx_timestamp = 14u;
    f.can_timestamp = 14u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 40u, 1u, &sample) == both);

    f.coolant_control = 0x41u;
    f.coolant_dlc = 7u;
    f.can_timestamp = 16u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 44u, 1u, &sample) == TA2005_CHERY_SPEED);
    assert(sample.speed_fad8 == 9600u && sample.coolant_f9e9 == UINT8_MAX);
    assert(sample.model.f9e8 == 0x96u);
    f.coolant_control = 0x41u;
    f.coolant_dlc = 8u;
    f.coolant_timestamp = 18u;
    f.can_timestamp = 18u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 47u, 1u, &sample) == both);

    /* Catch a complete OEM recovery even if the foreground never saw BusOff. */
    f.rx_control = 0;
    f.coolant_control = 0;
    f.can_timestamp = 0;
    f.stock_can_state = 7u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 50u, 1u, &sample) == 0u);
    assert(rx.phase == LFJ8_H03_RX_WAIT_FOR_OEM);
    assert(sample.model.f9d8 == UINT8_MAX && sample.model.f9e8 == UINT8_MAX && sample.model.f914 == UINT8_MAX);
    assert(lfj8_h03_engine_rx_poll(&rx, &io, start + 60u, 1u, &sample) == 0u);
    assert(f.rx_control == 0x40u && f.coolant_control == 0x40u);

    /* A skipped poll can leave a frame older than the whole 16-bit clock.
     * Its low stamp alone looks current, so require drainage and a new frame. */
    f.rx_control = 0x41u;
    f.rx_timestamp = 19u;
    f.can_timestamp = 20u;
    const uint32_t resumed = start + 132000u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed, 1u, &sample) == 0u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && f.rx_control == 0x41u);
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 10u, 1u, &sample) == 0u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && f.rx_control == 0x40u);
    f.can_timestamp = 25u;
    f.rx_timestamp = 24u;
    f.rpm_arrives_during_coolant_poll = 1u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 20u, 1u, &sample) == 0u);
    assert(f.rx_control == 0x41u && f.rpm_arrives_during_coolant_poll == 0u);
    f.coolant_control = 0x41u;
    f.coolant_timestamp = 26u;
    f.can_timestamp = 27u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 25u, 1u, &sample) == TA2005_CHERY_COOLANT);
    assert(sample.coolant_f9e9 == 137u && sample.model.f9e8 == UINT8_MAX);

    f.rx_control = 0x41u;
    f.rx_timestamp = 30u;
    f.can_timestamp = 30u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 30u, 1u, &sample) == both);
    assert(sample.speed_fad8 == 9600u);
    f.can_timestamp = 130u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 230u, 1u, &sample) == 0u);
    assert(sample.speed_fad8 == UINT16_MAX && sample.coolant_f9e9 == UINT8_MAX);
    assert(sample.model.f9d8 == UINT8_MAX && sample.model.f9e8 == UINT8_MAX && sample.model.f914 == UINT8_MAX);
    /* Once the initial window has elapsed, the software clock may wrap
     * without reapplying the initial anchor to a fresh pending frame. */
    assert(rx.phase == LFJ8_H03_RX_ACTIVE);
    rx.time_ticks = UINT32_MAX - 1u;
    f.rx_control = 0x41u;
    f.rx_timestamp = 131u;
    f.can_timestamp = 132u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 234u, 1u, &sample) == TA2005_CHERY_SPEED);
    assert(rx.time_ticks == 0u && sample.speed_fad8 == 9600u);

    f.can_status = 0x4000u;
    assert(lfj8_h03_engine_rx_poll(&rx, &io, resumed + 235u, 1u, &sample) == 0u);
    assert(rx.phase == LFJ8_H03_RX_WAIT_FOR_OEM && f.lock_depth == 0u);
}

static void test_capture_pair(void)
{
    Fixture f = {.capture_timer = UINT32_MAX - 1u, .capture_timer_read_step = 4u, .nt_timer = 25u};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    volatile Lfj8RawVss vss = {.last_edge = UINT32_MAX - 11u, .interval_ticks = 80u, .primed = 1u};
    volatile Lfj8RawCapture nt = {.last_edge = 20u, .interval_ticks = 20u, .primed = 1u};
    Lfj8CapturePair pair;
    assert(lfj8_h03_capture_pair(&vss, &nt, &io, 100u, 100u, 4u, &pair));
    assert(pair.now_tml0 == 0u && pair.vss_at_tml0 == UINT32_MAX - 11u);
    assert(pair.nt_at_tml0 == UINT32_MAX - 4u && pair.nt_edge_tml1 == 20u);
    assert(pair.nt_alignment_error_ticks == 2u);
    assert(pair.vss.state == LFJ8_VSS_VALID && pair.nt.state == LFJ8_VSS_VALID);
    assert(!lfj8_h03_capture_pair(&vss, &nt, &io, 100u, 100u, 3u, &pair));
    assert(pair.now_tml0 == 10u && pair.nt.state == LFJ8_VSS_UNAVAILABLE);
    f.nt_timer = 121u;
    assert(lfj8_h03_capture_pair(&vss, &nt, &io, 100u, 100u, 4u, &pair));
    assert(pair.nt.state == LFJ8_VSS_UNAVAILABLE && pair.vss.state == LFJ8_VSS_VALID);
    assert(f.lock_depth == 0u);
}

static void test_speed(void)
{
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(52800u, 2u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(105600u, 4u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2100000u, 2u, 3u, LFJ8_VSS_VALID) == 4200u);
    assert(lfj8_vss_raw_1ae(52800u, 4u, 1000000u, 2000000u, 1u, 2u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(26401u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 5999u);
    assert(lfj8_vss_raw_1ae(1u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(0u, 0u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_STOPPED) == 0u);
    assert(lfj8_vss_raw_1ae(1u, 1u, 1000000u, 2000000u, 1u, 0u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(100u, 3u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_UNAVAILABLE) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(1u, 4u, UINT32_MAX, UINT32_MAX, UINT16_MAX, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(UINT32_MAX, 1u, 1000000u, 2000000u, 1u, UINT16_MAX, LFJ8_VSS_VALID) == 0u);
}

static void test_packers(void)
{
    uint8_t payload[8];
    Lfj8Chery1ae status = {0};
    const uint8_t expected_1ae[] = {0x0F, 0x00, 0x11, 0x0F, 0x00, 0x00, 0x17, 0x70};
    const uint8_t expected_300[] = {0x0F, 0x00, 0x40, 0x01, 0x00, 0x00, 0x00, 0x00};

    status.flag_fd18_4 = 1u;
    assert(lfj8_pack_1ae(payload, &status, 6000u) == 1u);
    assert(memcmp(payload, expected_1ae, sizeof payload) == 0);
    status.raw_fa5f = 128u;
    status.counter_f8e4 = 255u;
    assert(lfj8_pack_1ae(payload, &status, 6000u) == 0u && payload[5] == 254u);
    status.flag_e026_0 = 1u;
    assert(lfj8_pack_1ae(payload, &status, 0xFFFFu) == 0u && payload[5] == 255u);
    lfj8_pack_300(payload, 0x0Fu, 0u, 1u, -39, 1u);
    assert(memcmp(payload, expected_300, sizeof payload) == 0);
    lfj8_pack_300(payload, 0u, 0u, 0u, 300, 1u);
    assert(payload[3] == 144u);
    lfj8_pack_300(payload, 0u, 0u, 0u, -300, 1u);
    assert(payload[3] == 0u);
    lfj8_pack_300(payload, 0u, 0u, 0u, 0, 0u);
    assert(payload[3] == 255u);

    assert(lfj8_relay_mask('R') == 3u);
    assert(lfj8_relay_mask('L') == 2u);
    assert(lfj8_relay_mask('D') == 0u && lfj8_relay_mask('N') == 0u && lfj8_relay_mask('P') == 0u);
}

static void test_schedule(void)
{
    Lfj8CherySchedule schedule;
    lfj8_schedule_init(&schedule, UINT32_MAX - 4000u, 10000u, 30000u);
    assert(lfj8_schedule_poll(&schedule, 5998u) == 0u);
    assert(lfj8_schedule_poll(&schedule, 5999u) == LFJ8_DUE_1AE);
    assert(lfj8_schedule_poll(&schedule, 26999u) == (LFJ8_DUE_1AE | LFJ8_DUE_300));
    assert(lfj8_schedule_poll(&schedule, 26999u) == 0u);
    assert(lfj8_schedule_poll(&schedule, 36000u) == LFJ8_DUE_1AE);

    lfj8_schedule_init(&schedule, 100u, 0u, 200u);
    assert(lfj8_schedule_poll(&schedule, 300u) == LFJ8_DUE_300);
}

static void test_donor_io(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    const uint8_t payload[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    const uint8_t blocked_values[] = {0x02u, 0x40u, 0x80u, 0x82u, 0x83u};

    f.interval = 26400u;
    f.pulse_count = 1u;
    f.freshness = 0x43610000u; /* 225.0f */
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_VALID);
    f.edge_count = 1u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    f.edge_count = 0u;
    f.freshness = 0x80000000u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    f.freshness = 0x7FC00000u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    assert(f.lock_count == 4u);

    assert(lfj8_can0_slot13_submit(&io, 0u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_NOT_OWNED);
    assert(lfj8_can0_slot13_submit(&io, 1u, 0x123u, payload) == LFJ8_CAN_WRONG_FRAME);
    assert(f.lock_count == 4u);
    f.can_control = 1u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_control = 0u;
    f.can_status = 0x4000u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_status = 0u;
    f.formats = 0x0004u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_NOT_STANDARD);
    f.formats = 0u;
    f.can_mode = 2u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_mode = 0u;
    for (unsigned i = 0u; i < sizeof blocked_values; ++i) {
        f.slot_control = blocked_values[i];
        assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_BUSY);
    }
    assert(f.writes == 0u);
    f.slot_control = 0x81u;
    f.slot_clear_fails = 1u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_BUSY);
    assert(f.writes == 1u && f.submissions == 0u);
    f.slot_control = 0x81u;
    f.slot_clear_fails = 0u;
    f.can_control = 0x0008u;
    f.can_status = 0x0800u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SUBMITTED);
    assert(f.last_sid[0] == 0x06u && f.last_sid[1] == 0x2Eu && f.last_dlc == 8u);
    assert(memcmp(f.last_data, payload, sizeof payload) == 0);
    assert(f.writes == 14u && f.submissions == 1u && f.lock_depth == 0u);
}

static void test_raw_capture(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    volatile Lfj8RawVss tracker;
    const uint32_t expiry = 500000u;
    Lfj8CaptureSnapshot sample;

    lfj8_9e1b_raw_vss_init(&tracker);
    f.capture_timer = UINT32_MAX - 149999u;
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    f.capture_timer = 150000u;
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    sample = lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry);
    assert(sample.state == LFJ8_VSS_VALID && sample.pulse_window == 1u);
    assert(sample.interval_ticks == 300000u);
    assert(lfj8_vss_raw_1ae(sample.interval_ticks, 1u, 1000000u, 2000000u,
                           1u, 1u, sample.state) == 528u);
    f.capture_timer += expiry + 1u;
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
}

static void test_9e1c_capture(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    volatile Lfj8RawVss tracker;
    const uint32_t expiry = 500000u;
    Lfj8CaptureSnapshot sample;
    uint32_t saved_state;

    f.use_9e1c_vss_map = 1u;
    f.interval = 26400u;
    f.pulse_count = 1u;
    f.freshness = 0x43610000u;
    f.edge_count = 1u;
    assert(lfj8_9e1c_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    f.edge_count = 0u;
    sample = lfj8_9e1c_capture_snapshot(&io);
    assert(sample.state == LFJ8_VSS_VALID && sample.interval_ticks == 26400u);
    assert(sample.pulse_window == 1u);
    f.freshness = 0u;
    assert(lfj8_9e1c_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);

    lfj8_9e1c_raw_vss_init(&tracker);
    f.captured_ticks = UINT32_MAX - 149999u;
    f.capture_timer = f.captured_ticks + 10u;
    saved_state = lock(&f);
    lfj8_9e1c_raw_vss_after_capture_store(&tracker, &io, expiry);
    lfj8_9e1c_raw_vss_after_capture_store(&tracker, &io, expiry);
    unlock(&f, saved_state);
    assert(lfj8_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);

    f.captured_ticks = 150000u;
    f.capture_timer = f.captured_ticks + 20u;
    saved_state = lock(&f);
    lfj8_9e1c_raw_vss_after_capture_store(&tracker, &io, expiry);
    unlock(&f, saved_state);
    sample = lfj8_raw_vss_snapshot(&tracker, &io, expiry);
    assert(sample.state == LFJ8_VSS_VALID && sample.interval_ticks == 300000u);
    assert(sample.pulse_window == 1u);
    assert(lfj8_raw_vss_snapshot(&tracker, &io, expiry).interval_ticks == 300000u);
    assert(f.writes == 0u && f.lock_depth == 0u);

    Lfj8CheryTx tx;
    const Lfj8VehicleCalibration cal = {1000000u, expiry, 2000000u, 1u, 1u};
    const Lfj8CheryTxInputs inputs = {0};
    lfj8_chery_tx_init(&tx, 0u, 10000u, 30000u);
    f.can_control = 0x0008u;
    f.can_status = 0x0800u;
    assert(lfj8_chery_tx_poll(&tx, &io, 10000u, 1u, &tracker, &cal, &inputs) == LFJ8_DUE_1AE);
    assert(f.last_data[6] == 0x02u && f.last_data[7] == 0x10u);

    f.capture_timer = f.captured_ticks + expiry + 1u;
    assert(lfj8_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    assert(f.submissions == 1u && f.lock_depth == 0u);
}

static void test_9e1c_nt_capture(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    volatile Lfj8RawCapture tracker;
    const uint32_t expiry = 50000u;
    lfj8_9e1c_raw_nt_init(&tracker);

    f.nt_captured_ticks = UINT32_MAX - 99u;
    f.nt_timer = f.nt_captured_ticks;
    uint32_t saved_state = lock(&f);
    lfj8_9e1c_raw_nt_after_capture_store(&tracker, &io, expiry);
    lfj8_9e1c_raw_nt_after_capture_store(&tracker, &io, expiry);
    unlock(&f, saved_state);
    assert(lfj8_9e1c_raw_nt_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);

    f.nt_captured_ticks = 300u;
    f.nt_timer = 301u;
    saved_state = lock(&f);
    lfj8_9e1c_raw_nt_after_capture_store(&tracker, &io, expiry);
    unlock(&f, saved_state);
    const Lfj8CaptureSnapshot sample = lfj8_9e1c_raw_nt_snapshot(&tracker, &io, expiry);
    assert(sample.state == LFJ8_VSS_VALID && sample.interval_ticks == 400u && sample.pulse_window == 1u);

    f.nt_timer = f.nt_captured_ticks + expiry + 1u;
    assert(lfj8_9e1c_raw_nt_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    assert(f.writes == 0u && f.lock_depth == 0u);
}

static void test_pipeline(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    const Lfj8VehicleCalibration cal = {1000000u, 500000u, 2000000u, 1u, 1u};
    Lfj8CheryTxInputs inputs = {0};
    Lfj8CheryTx tx;
    volatile Lfj8RawVss vss;

    lfj8_chery_tx_init(&tx, 0u, 10000u, 30000u);
    lfj8_9e1b_raw_vss_init(&vss);
    lfj8_9e1b_raw_vss_edge(&vss, 0u, cal.vss_timeout_ticks);
    lfj8_9e1b_raw_vss_edge(&vss, 26400u, cal.vss_timeout_ticks);
    f.capture_timer = 26400u;
    inputs.status_1ae.flag_fd18_4 = 1u;
    inputs.status0_300 = 0x0Fu;
    inputs.flag_fd18_9 = 1u;
    inputs.atf_c = 80;
    inputs.atf_valid = 1u;

    assert(lfj8_chery_tx_poll(&tx, &io, 9999u, 1u, &vss, &cal, &inputs) == 0u);
    f.slot_control = 0x80u;
    assert(lfj8_chery_tx_poll(&tx, &io, 10000u, 1u, &vss, &cal, &inputs) == 0u);
    assert(tx.pending == LFJ8_DUE_1AE && tx.counter_f8e4 == 0u);
    f.slot_control = 0u;
    assert(lfj8_chery_tx_poll(&tx, &io, 10001u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_1AE);
    assert(f.last_data[6] == 0x17u && f.last_data[7] == 0x70u && tx.counter_f8e4 == 1u);

    f.slot_control = 0x81u;
    assert(lfj8_chery_tx_poll(&tx, &io, 30000u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_300);
    assert(f.last_sid[0] == 0x0Cu && f.last_sid[1] == 0u);
    assert(f.last_data[3] == 120u && tx.pending == LFJ8_DUE_1AE && tx.counter_f8e4 == 1u);
    f.slot_control = 0x81u;
    f.capture_timer += cal.vss_timeout_ticks + 1u;
    assert(lfj8_chery_tx_poll(&tx, &io, 30001u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_1AE);
    assert(f.last_data[6] == 0xFFu && f.last_data[7] == 0xFFu && tx.counter_f8e4 == 2u);
    assert(lfj8_chery_tx_poll(&tx, &io, 40000u, 0u, &vss, &cal, &inputs) == 0u);
    assert(tx.pending == 0u && tx.counter_f8e4 == 0u && f.submissions == 3u);
}

static void test_engine_receive(void)
{
    Ta2005CheryInputs receiver;
    Ta2005CherySnapshot snapshot;
    uint8_t frame[8] = {0};
    uint32_t received_at = UINT32_MAX - 1u;
    uint32_t now = 2u;
    ta2005_chery_inputs_reset(&receiver);
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot) == 0);

    for (unsigned int raw = 0; raw <= UINT16_MAX; ++raw) {
        frame[0] = (uint8_t)(raw >> 8);
        frame[1] = (uint8_t)raw;
        frame[2] = (uint8_t)(raw >> 8);
        frame[3] = (uint8_t)(raw ^ (raw >> 8));
        frame[5] = (uint8_t)(raw + 1u);
        frame[4] = (uint8_t)~frame[2];
        frame[6] = (uint8_t)~frame[3];
        frame[7] = (uint8_t)~frame[5];
        assert(ta2005_chery_inputs_receive(&receiver, 0x0fau, 8, frame, &received_at) ==
               TA2005_CHERY_SPEED);
        const unsigned int expected = raw == UINT16_MAX ? UINT16_MAX :
            (raw > 32767u ? 65534u : raw * 2u);
        const unsigned int valid = ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot);
        assert(valid == (raw == UINT16_MAX ? 0u : TA2005_CHERY_SPEED));
        assert(snapshot.speed_fad8 == expected);
        assert(snapshot.model.f9d8 == frame[2] && snapshot.model.f9e8 == frame[3] &&
               snapshot.model.f914 == frame[5]);
    }

    for (unsigned int raw = 0; raw <= UINT8_MAX; ++raw) {
        frame[0] = (uint8_t)raw;
        assert(ta2005_chery_inputs_receive(&receiver, 0x278u, 8, frame, &received_at) ==
               TA2005_CHERY_COOLANT);
        const unsigned int expected = raw == UINT8_MAX ? UINT8_MAX : raw * 3u / 4u + 2u;
        const unsigned int valid = ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot);
        assert(valid == (raw == UINT8_MAX ? 0u : TA2005_CHERY_COOLANT));
        assert(snapshot.coolant_f9e9 == expected);
    }

    const uint8_t rpm[8] = {0x12u, 0xc0u, 0xffu, 0xffu, 0u, 0xffu};
    const uint8_t coolant[8] = {0xb4u, 0xffu, 0xffu, 0xffu, 0xffu, 0xffu, 0xffu, 0xffu};
    received_at = 1;
    assert(ta2005_chery_inputs_receive(&receiver, 0xfau, 8, rpm, &received_at));
    received_at = 2;
    assert(!ta2005_chery_inputs_receive(&receiver, 0x278u, 7, coolant, &received_at));
    assert(!ta2005_chery_inputs_receive(&receiver, 0x270u, 8, coolant, &received_at));
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot) == TA2005_CHERY_SPEED);
    assert(ta2005_chery_inputs_receive(&receiver, 0x278u, 8, coolant, &received_at));
    received_at = UINT32_MAX;
    assert(!ta2005_chery_inputs_receive(&receiver, 0x0fau, 8, frame, &received_at));
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot) ==
           (TA2005_CHERY_SPEED | TA2005_CHERY_COOLANT));
    assert(snapshot.speed_fad8 == 9600u && snapshot.coolant_f9e9 == 137u);
    assert(snapshot.model.f9d8 == UINT8_MAX && snapshot.model.f9e8 == UINT8_MAX &&
           snapshot.model.f914 == UINT8_MAX);
    now = 6;
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot) == TA2005_CHERY_COOLANT);
    now = 7;
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 5, &snapshot) == 0);
    ta2005_chery_inputs_reset(&receiver);
    assert(ta2005_chery_inputs_snapshot(&receiver, &received_at, 5, &snapshot) == 0);
}

int main(void)
{
    test_speed();
    test_packers();
    test_schedule();
    test_donor_io();
    test_can_receive_assignment();
    test_can_receive();
    test_engine_can_lifecycle();
    test_capture_pair();
    test_raw_capture();
    test_9e1c_capture();
    test_9e1c_nt_capture();
    test_pipeline();
    test_engine_receive();
    puts("LFJ8 I/O: S51, S83, Chery TX, CAN0 RX/TX and recovery, RPM/ECT, relays and schedule passed");
    return 0;
}
