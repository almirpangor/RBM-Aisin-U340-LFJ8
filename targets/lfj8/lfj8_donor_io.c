#include "lfj8_donor_io.h"
#include "lfj8_bridge.h"

#define LFJ8_9E1B_VSS_INTERVAL UINT32_C(0x806164)
#define LFJ8_9E1B_VSS_EDGES_TO_LOCK UINT32_C(0x8061C4)
#define LFJ8_9E1B_VSS_PULSE_WINDOW UINT32_C(0x8061CC)
#define LFJ8_9E1C_VSS_INTERVAL UINT32_C(0x80616C)
#define LFJ8_9E1C_VSS_EDGES_TO_LOCK UINT32_C(0x8061CC)
#define LFJ8_9E1C_VSS_PULSE_WINDOW UINT32_C(0x8061D4)
#define LFJ8_9E1C_VSS_CAPTURED_TICKS UINT32_C(0x8048B8)
#define LFJ8_VSS_FRESHNESS UINT32_C(0x804EC4)
#define LFJ8_VSS_TIMER_NOW UINT32_C(0x8003E0)
#define LFJ8_9E1C_NT_CAPTURED_TICKS UINT32_C(0x8048BC)
#define LFJ8_9E1C_NT_TIMER_NOW UINT32_C(0x800FE0)
#define LFJ8_CAN0_MODE UINT32_C(0x801018)
#define LFJ8_CAN0_CNT UINT32_C(0x801000)
#define LFJ8_CAN0_STAT UINT32_C(0x801002)
#define LFJ8_CAN0_FFS UINT32_C(0x80101C)
#define LFJ8_CAN0_FFS_IDE13 UINT32_C(0x00040000)
#define LFJ8_CAN0_SLOT13_CNT UINT32_C(0x80105D)
#define LFJ8_CAN0_SLOT13_SID0 UINT32_C(0x8011D0)
#define LFJ8_CAN0_SLOT13_SID1 UINT32_C(0x8011D1)
#define LFJ8_CAN0_SLOT13_DLC UINT32_C(0x8011D5)
#define LFJ8_CAN0_SLOT13_DATA UINT32_C(0x8011D6)

enum {
    CAN_CNT_FRST = 0x0010,
    CAN_CNT_LBM = 0x0002,
    CAN_CNT_RST = 0x0001,
    CAN_STAT_BOS = 0x4000,
    CAN_STAT_LBS = 0x0200,
    CAN_STAT_CRS = 0x0100,
    CAN_SLOT_TR = 0x80,
    CAN_SLOT_TRFIN = 0x01,
};

static Lfj8CaptureSnapshot capture_snapshot(const Lfj8RegisterIo *io,
                                            uint32_t interval_address,
                                            uint32_t pulse_window_address,
                                            uint32_t edge_lock_address)
{
    Lfj8CaptureSnapshot snapshot;
    uint32_t freshness;
    uint16_t edges_to_lock;
    const uint32_t saved_state = io->enter(io->context);
    snapshot.interval_ticks = io->read32(io->context, interval_address);
    snapshot.pulse_window = io->read16(io->context, pulse_window_address);
    edges_to_lock = io->read16(io->context, edge_lock_address);
    freshness = io->read32(io->context, LFJ8_VSS_FRESHNESS);
    io->leave(io->context, saved_state);

    /* Positive finite IEEE-754 freshness, plus the OEM edge-lock condition. */
    snapshot.state = LFJ8_VSS_UNAVAILABLE;
    if (edges_to_lock == 0u && freshness != 0u && freshness < UINT32_C(0x7F800000) &&
        snapshot.interval_ticks != 0u && (snapshot.pulse_window == 1u ||
        snapshot.pulse_window == 2u || snapshot.pulse_window == 4u)) {
        snapshot.state = LFJ8_VSS_VALID;
    }
    return snapshot;
}

Lfj8CaptureSnapshot lfj8_9e1b_capture_snapshot(const Lfj8RegisterIo *io)
{
    return capture_snapshot(io, LFJ8_9E1B_VSS_INTERVAL, LFJ8_9E1B_VSS_PULSE_WINDOW,
                            LFJ8_9E1B_VSS_EDGES_TO_LOCK);
}

Lfj8CaptureSnapshot lfj8_9e1c_capture_snapshot(const Lfj8RegisterIo *io)
{
    return capture_snapshot(io, LFJ8_9E1C_VSS_INTERVAL, LFJ8_9E1C_VSS_PULSE_WINDOW,
                            LFJ8_9E1C_VSS_EDGES_TO_LOCK);
}

static void raw_capture_init(volatile Lfj8RawCapture *capture)
{
    capture->last_edge = 0u;
    capture->interval_ticks = 0u;
    capture->primed = 0u;
}

static void raw_capture_edge(volatile Lfj8RawCapture *capture, uint32_t captured_ticks,
                             uint32_t timeout_ticks)
{
    if (capture->primed != 0u) {
        const uint32_t elapsed = captured_ticks - capture->last_edge;
        if (elapsed == 0u) {
            return;
        }
        capture->interval_ticks = elapsed <= timeout_ticks ? elapsed : 0u;
    }
    capture->last_edge = captured_ticks;
    capture->primed = 1u;
}

static Lfj8CaptureSnapshot raw_capture_snapshot(volatile Lfj8RawCapture *capture,
                                                const Lfj8RegisterIo *io, uint32_t timer_address,
                                                uint32_t timeout_ticks)
{
    Lfj8CaptureSnapshot snapshot = {0u, 1u, LFJ8_VSS_UNAVAILABLE};
    const uint32_t saved_state = io->enter(io->context);
    const uint32_t now = io->read32(io->context, timer_address);

    if (capture->primed != 0u) {
        if (timeout_ticks == 0u || now - capture->last_edge > timeout_ticks) {
            raw_capture_init(capture);
        } else if (capture->interval_ticks != 0u && capture->interval_ticks <= timeout_ticks) {
            snapshot.interval_ticks = capture->interval_ticks;
            snapshot.state = LFJ8_VSS_VALID;
        }
    }
    io->leave(io->context, saved_state);
    return snapshot;
}

Lfj8CaptureSnapshot lfj8_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                         const Lfj8RegisterIo *io,
                                         uint32_t timeout_ticks)
{
    return raw_capture_snapshot(vss, io, LFJ8_VSS_TIMER_NOW, timeout_ticks);
}

void lfj8_9e1b_raw_vss_init(volatile Lfj8RawVss *vss)
{
    raw_capture_init(vss);
}

void lfj8_9e1b_raw_vss_edge(volatile Lfj8RawVss *vss, uint32_t captured_ticks,
                           uint32_t timeout_ticks)
{
    raw_capture_edge(vss, captured_ticks, timeout_ticks);
}

Lfj8CaptureSnapshot lfj8_9e1b_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                             const Lfj8RegisterIo *io,
                                             uint32_t timeout_ticks)
{
    return lfj8_raw_vss_snapshot(vss, io, timeout_ticks);
}

void lfj8_9e1c_raw_vss_init(volatile Lfj8RawVss *vss)
{
    raw_capture_init(vss);
}

void lfj8_9e1c_raw_vss_after_capture_store(volatile Lfj8RawVss *vss,
                                         const Lfj8RegisterIo *io,
                                         uint32_t timeout_ticks)
{
    const uint32_t captured_ticks = io->read32(io->context, LFJ8_9E1C_VSS_CAPTURED_TICKS);

    raw_capture_edge(vss, captured_ticks, timeout_ticks);
}

void lfj8_9e1c_raw_nt_init(volatile Lfj8RawCapture *nt)
{
    raw_capture_init(nt);
}

void lfj8_9e1c_raw_nt_after_capture_store(volatile Lfj8RawCapture *nt,
                                        const Lfj8RegisterIo *io, uint32_t timeout_ticks)
{
    const uint32_t captured_ticks = io->read32(io->context, LFJ8_9E1C_NT_CAPTURED_TICKS);
    raw_capture_edge(nt, captured_ticks, timeout_ticks);
}

Lfj8CaptureSnapshot lfj8_9e1c_raw_nt_snapshot(volatile Lfj8RawCapture *nt,
                                            const Lfj8RegisterIo *io, uint32_t timeout_ticks)
{
    return raw_capture_snapshot(nt, io, LFJ8_9E1C_NT_TIMER_NOW, timeout_ticks);
}

static uint8_t can0_available(const Lfj8RegisterIo *io)
{
    /* BasicCAN affects only slots 30/31 (Renesas §§13.2.2–13.2.3). */
    return (io->read16(io->context, LFJ8_CAN0_CNT) &
            (CAN_CNT_FRST | CAN_CNT_LBM | CAN_CNT_RST)) == 0u &&
           (io->read16(io->context, LFJ8_CAN0_STAT) &
            (CAN_STAT_BOS | CAN_STAT_LBS | CAN_STAT_CRS)) == 0u &&
           (io->read8(io->context, LFJ8_CAN0_MODE) & 3u) == 0u;
}

static Lfj8CanResult write_if_idle(const Lfj8RegisterIo *io, uint16_t id,
                                  const uint8_t payload[8])
{
    uint8_t control;
    uint32_t i;

    if (!can0_available(io)) {
        return LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    }
    if ((io->read32(io->context, LFJ8_CAN0_FFS) & LFJ8_CAN0_FFS_IDE13) != 0u) {
        return LFJ8_CAN_SLOT_NOT_STANDARD;
    }

    /* A completed slot can retain TR. A pending request has no TRFIN. */
    control = io->read8(io->context, LFJ8_CAN0_SLOT13_CNT);
    if (control != 0u && control != CAN_SLOT_TRFIN &&
        control != (CAN_SLOT_TR | CAN_SLOT_TRFIN)) {
        return LFJ8_CAN_SLOT_BUSY;
    }
    io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, 0u);
    if (io->read8(io->context, LFJ8_CAN0_SLOT13_CNT) != 0u) {
        return LFJ8_CAN_SLOT_BUSY;
    }

    io->write8(io->context, LFJ8_CAN0_SLOT13_SID0, (uint8_t)(id >> 6));
    io->write8(io->context, LFJ8_CAN0_SLOT13_SID1, (uint8_t)(id & 0x3Fu));
    io->write8(io->context, LFJ8_CAN0_SLOT13_DLC, 8u);
    for (i = 0u; i < 8u; ++i) {
        io->write8(io->context, LFJ8_CAN0_SLOT13_DATA + i, payload[i]);
    }

    if (!can0_available(io)) {
        return LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    }
    io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, CAN_SLOT_TR);
    return LFJ8_CAN_SUBMITTED;
}

Lfj8CanResult lfj8_can0_slot13_submit(const Lfj8RegisterIo *io, uint8_t slot13_owned,
                                     uint16_t id, const uint8_t payload[8])
{
    uint32_t saved_state;
    Lfj8CanResult result;

    if (slot13_owned == 0u) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    if (id != LFJ8_CAN_1AE && id != LFJ8_CAN_300) {
        return LFJ8_CAN_WRONG_FRAME;
    }

    saved_state = io->enter(io->context);
    result = write_if_idle(io, id, payload);
    io->leave(io->context, saved_state);
    return result;
}
