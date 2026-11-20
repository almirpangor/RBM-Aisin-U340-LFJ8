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
#define LFJ8_CAN0_EXTID UINT32_C(0x801004)
#define LFJ8_CAN0_TSTMP UINT32_C(0x801008)
#define LFJ8_CAN0_EXTID_IDE13 UINT16_C(0x0004)
#define LFJ8_CAN0_SLIMK_TX13 UINT16_C(0x0004)
#define LFJ8_CAN0_SLIST UINT32_C(0x80100C)
#define LFJ8_CAN0_SLIMK UINT32_C(0x801010)
#define LFJ8_CAN0_BASIC_RX_BITS UINT16_C(0x0003)
#define LFJ8_CAN0_GMSKS0 UINT32_C(0x801028)
#define LFJ8_CAN0_GMSKS1 UINT32_C(0x801029)
#define LFJ8_CAN0_ENGINE_SLOT_BITS UINT16_C(0x0018)
#define LFJ8_H03_CAN0_OEM_STATE UINT32_C(0x806AE6)
#define LFJ8_CAN0_SLOT_CNT UINT32_C(0x801050)
#define LFJ8_CAN0_SLOT_DATA UINT32_C(0x801100)
#define LFJ8_CAN0_SLOT13_CNT UINT32_C(0x80105D)
#define LFJ8_CAN0_SLOT13_SID0 UINT32_C(0x8011D0)
#define LFJ8_CAN0_SLOT13_SID1 UINT32_C(0x8011D1)
#define LFJ8_CAN0_SLOT13_DLC UINT32_C(0x8011D5)
#define LFJ8_CAN0_SLOT13_DATA UINT32_C(0x8011D6)
#define LFJ8_CAN0_SLOT13_TIMESTAMP UINT32_C(0x8011DE)
#define LFJ8_CAN_DIAG_REPLY UINT16_C(0x722)
#define LFJ8_CAN_TORQUE_REQUEST UINT16_C(0x5E8)
#define LFJ8_CAN_TORQUE_STATUS UINT16_C(0x5E9)

enum {
    CAN_CNT_TSR = 0x0400,
    CAN_CNT_TSP = 0x0300,
    CAN_CNT_FRST = 0x0010,
    CAN_CNT_LBM = 0x0002,
    CAN_CNT_RST = 0x0001,
    CAN_STAT_BOS = 0x4000,
    CAN_STAT_BASIC = 0x0800,
    CAN_STAT_LBS = 0x0200,
    CAN_STAT_CRS = 0x0100,
    CAN_SLOT_TR = 0x80,
    CAN_SLOT_RR = 0x40,
    CAN_SLOT_ML = 0x04,
    CAN_SLOT_TRSTAT = 0x02,
    CAN_SLOT_TRFIN = 0x01,
    CAN_SLOT_CLEAR_RX = 0x4e,
    CAN_SLOT_ABORT_TX = 0x0f,
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

static Lfj8CaptureSnapshot raw_capture_at(volatile Lfj8RawCapture *capture,
                                         uint32_t now, uint32_t timeout_ticks)
{
    Lfj8CaptureSnapshot snapshot = {0u, 1u, LFJ8_VSS_UNAVAILABLE};

    if (capture->primed != 0u) {
        if (timeout_ticks == 0u || now - capture->last_edge > timeout_ticks) {
            raw_capture_init(capture);
        } else if (capture->interval_ticks != 0u && capture->interval_ticks <= timeout_ticks) {
            snapshot.interval_ticks = capture->interval_ticks;
            snapshot.state = LFJ8_VSS_VALID;
        }
    }
    return snapshot;
}

static Lfj8CaptureSnapshot raw_capture_snapshot(volatile Lfj8RawCapture *capture,
                                                const Lfj8RegisterIo *io, uint32_t timer_address,
                                                uint32_t timeout_ticks, uint8_t standstill_confirmed)
{
    const uint32_t saved_state = io->enter(io->context);
    Lfj8CaptureSnapshot snapshot =
        raw_capture_at(capture, io->read32(io->context, timer_address), timeout_ticks);
    /* A fresh first edge has no speed interval yet, but excludes standstill. */
    if (standstill_confirmed == 1u && capture->primed == 0u &&
        timeout_ticks != 0u && timeout_ticks < UINT32_C(0x80000000)) {
        snapshot.state = LFJ8_VSS_STOPPED;
    }
    io->leave(io->context, saved_state);
    return snapshot;
}

Lfj8CaptureSnapshot lfj8_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                         const Lfj8RegisterIo *io,
                                         uint32_t timeout_ticks)
{
    return raw_capture_snapshot(vss, io, LFJ8_VSS_TIMER_NOW, timeout_ticks, 0u);
}

Lfj8CaptureSnapshot lfj8_raw_vss_snapshot_with_standstill(
    volatile Lfj8RawVss *vss, const Lfj8RegisterIo *io, uint32_t timeout_ticks,
    uint8_t standstill_confirmed)
{
    return raw_capture_snapshot(vss, io, LFJ8_VSS_TIMER_NOW, timeout_ticks, standstill_confirmed);
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
    return raw_capture_snapshot(nt, io, LFJ8_9E1C_NT_TIMER_NOW, timeout_ticks, 0u);
}

int lfj8_h03_capture_pair(volatile Lfj8RawVss *vss, volatile Lfj8RawCapture *nt,
                          const Lfj8RegisterIo *io, uint32_t vss_timeout_ticks,
                          uint32_t nt_timeout_ticks, uint16_t max_read_span_ticks,
                          Lfj8CapturePair *pair)
{
    pair->vss = (Lfj8CaptureSnapshot){0u, 1u, LFJ8_VSS_UNAVAILABLE};
    pair->nt = (Lfj8CaptureSnapshot){0u, 1u, LFJ8_VSS_UNAVAILABLE};
    pair->now_tml0 = 0u;
    pair->vss_at_tml0 = 0u;
    pair->nt_at_tml0 = 0u;
    pair->nt_edge_tml1 = 0u;
    pair->nt_alignment_error_ticks = 0u;

    const uint32_t saved = io->enter(io->context);
    const uint32_t before = io->read32(io->context, LFJ8_VSS_TIMER_NOW);
    const uint32_t nt_now = io->read32(io->context, LFJ8_9E1C_NT_TIMER_NOW);
    const uint32_t after = io->read32(io->context, LFJ8_VSS_TIMER_NOW);
    const uint32_t span = after - before;
    const int coherent = span <= max_read_span_ticks;
    pair->now_tml0 = after;
    if (coherent) {
        pair->now_tml0 = before + span / 2u;
        pair->vss = raw_capture_at(vss, pair->now_tml0, vss_timeout_ticks);
        pair->nt = raw_capture_at(nt, nt_now, nt_timeout_ticks);
        if (pair->vss.state == LFJ8_VSS_VALID) {
            pair->vss_at_tml0 = vss->last_edge;
        }
        if (pair->nt.state == LFJ8_VSS_VALID) {
            pair->nt_edge_tml1 = nt->last_edge;
            pair->nt_at_tml0 = pair->now_tml0 - (nt_now - pair->nt_edge_tml1);
            pair->nt_alignment_error_ticks = (uint16_t)((span + 1u) / 2u);
        }
    }
    io->leave(io->context, saved);
    return coherent;
}

static uint8_t can0_available(const Lfj8RegisterIo *io)
{
    /* On the 32176, BasicCAN is confined to slots 14 and 15. */
    return (io->read16(io->context, LFJ8_CAN0_CNT) &
            (CAN_CNT_FRST | CAN_CNT_LBM | CAN_CNT_RST)) == 0u &&
           (io->read16(io->context, LFJ8_CAN0_STAT) &
            (CAN_STAT_BOS | CAN_STAT_LBS | CAN_STAT_CRS)) == 0u &&
           (io->read8(io->context, LFJ8_CAN0_MODE) & 3u) == 0u;
}

static uint8_t h03_can0_operational(const Lfj8RegisterIo *io)
{
    const uint8_t state = io->read8(io->context, LFJ8_H03_CAN0_OEM_STATE);
    return (state == 6u || state == 7u) && can0_available(io) &&
        (io->read16(io->context, LFJ8_CAN0_CNT) & (CAN_CNT_TSR | CAN_CNT_TSP)) == 0u;
}

int lfj8_h03_can0_read_timestamp(const Lfj8RegisterIo *io, uint16_t *timestamp)
{
    const uint32_t saved_state = io->enter(io->context);
    const int running = h03_can0_operational(io);
    *timestamp = running ? io->read16(io->context, LFJ8_CAN0_TSTMP) : 0u;
    io->leave(io->context, saved_state);
    return running;
}

static int fullcan_receive_mode(const Lfj8RegisterIo *io, uint8_t slot, uint8_t control)
{
    const uint8_t allowed = CAN_SLOT_RR | CAN_SLOT_TRFIN | CAN_SLOT_TRSTAT | CAN_SLOT_ML;
    return (control & CAN_SLOT_RR) != 0u && (control & (uint8_t)~allowed) == 0u &&
           (io->read16(io->context, LFJ8_CAN0_EXTID) & (UINT16_C(0x8000) >> slot)) == 0u;
}

static Lfj8CanRxResult receive8(const Lfj8RegisterIo *io, uint8_t slot, Lfj8CanData8 *frame)
{
    if (!can0_available(io)) {
        return LFJ8_CAN_RX_UNAVAILABLE;
    }
    const uint32_t control_address = LFJ8_CAN0_SLOT_CNT + slot;
    const uint8_t control = io->read8(io->context, control_address);
    if (!fullcan_receive_mode(io, slot, control)) {
        return LFJ8_CAN_RX_WRONG_SLOT;
    }
    if ((control & CAN_SLOT_TRSTAT) != 0u) {
        return LFJ8_CAN_RX_RETRY;
    }
    if ((control & CAN_SLOT_ML) != 0u) {
        io->write8(io->context, control_address, CAN_SLOT_RR);
        return LFJ8_CAN_RX_LOST;
    }
    if ((control & CAN_SLOT_TRFIN) == 0u) {
        return LFJ8_CAN_RX_IDLE;
    }

    /* Renesas §13.6.3: keep receive armed and clear TRFIN before the copy. */
    io->write8(io->context, control_address, CAN_SLOT_CLEAR_RX);
    const uint32_t address = LFJ8_CAN0_SLOT_DATA + (uint32_t)slot * 16u;
    const uint8_t length = io->read8(io->context, address + 5u) & 0x0fu;
    Lfj8CanData8 pending;
    pending.id = 0u;
    pending.timestamp = 0u;
    if (length == 8u) {
        const uint32_t upper = io->read8(io->context, address) & 0x1fu;
        pending.id = (uint16_t)((upper << 6) | (io->read8(io->context, address + 1u) & 0x3fu));
        for (uint32_t index = 0; index < 8u; ++index) {
            pending.payload[index] = io->read8(io->context, address + 6u + index);
        }
        pending.timestamp = io->read16(io->context, address + 14u);
    }
    const uint8_t after = io->read8(io->context, control_address);
    if (!can0_available(io)) {
        return LFJ8_CAN_RX_UNAVAILABLE;
    }
    if (!fullcan_receive_mode(io, slot, after)) {
        return LFJ8_CAN_RX_WRONG_SLOT;
    }
    if ((after & CAN_SLOT_ML) != 0u) {
        return LFJ8_CAN_RX_LOST;
    }
    if ((after & (CAN_SLOT_TRFIN | CAN_SLOT_TRSTAT)) != 0u) {
        return LFJ8_CAN_RX_RETRY;
    }
    if (length != 8u) {
        return LFJ8_CAN_RX_BAD_LENGTH;
    }
    frame->id = pending.id;
    frame->timestamp = pending.timestamp;
    for (uint32_t index = 0; index < 8u; ++index) {
        frame->payload[index] = pending.payload[index];
    }
    return LFJ8_CAN_RX_RECEIVED;
}

Lfj8CanRxResult lfj8_can0_receive8(const Lfj8RegisterIo *io, uint8_t slot, uint8_t slot_owned,
                                 Lfj8CanData8 *frame)
{
    frame->id = 0u;
    frame->timestamp = 0u;
    for (uint32_t index = 0; index < 8u; ++index) {
        frame->payload[index] = 0u;
    }
    if (slot_owned != 1u || slot >= 14u) {
        return LFJ8_CAN_RX_WRONG_SLOT;
    }
    const uint32_t saved_state = io->enter(io->context);
    const Lfj8CanRxResult result = receive8(io, slot, frame);
    io->leave(io->context, saved_state);
    return result;
}

int lfj8_h03_can0_arm_engine_rx(const Lfj8RegisterIo *io, uint8_t slots_owned)
{
    if (slots_owned != 1u) {
        return 0;
    }
    const uint32_t rpm_control = LFJ8_CAN0_SLOT_CNT + LFJ8_H03_CAN0_RPM_SLOT;
    const uint32_t coolant_control = LFJ8_CAN0_SLOT_CNT + LFJ8_H03_CAN0_COOLANT_SLOT;
    const uint32_t saved_state = io->enter(io->context);
    int armed = 0;
    if (can0_available(io) &&
        (io->read16(io->context, LFJ8_CAN0_EXTID) & LFJ8_CAN0_ENGINE_SLOT_BITS) == 0u &&
        (io->read16(io->context, LFJ8_CAN0_SLIMK) & LFJ8_CAN0_ENGINE_SLOT_BITS) == 0u &&
        io->read8(io->context, LFJ8_CAN0_GMSKS0) == 0x1fu &&
        io->read8(io->context, LFJ8_CAN0_GMSKS1) == 0x3fu &&
        io->read8(io->context, rpm_control) == 0u &&
        io->read8(io->context, coolant_control) == 0u) {
        const uint32_t rpm_data = LFJ8_CAN0_SLOT_DATA + LFJ8_H03_CAN0_RPM_SLOT * 16u;
        const uint32_t coolant_data = LFJ8_CAN0_SLOT_DATA + LFJ8_H03_CAN0_COOLANT_SLOT * 16u;
        io->write8(io->context, rpm_data, 0x03u);
        io->write8(io->context, rpm_data + 1u, 0x3au);
        io->write8(io->context, coolant_data, 0x09u);
        io->write8(io->context, coolant_data + 1u, 0x38u);
        if (can0_available(io) &&
            io->read8(io->context, rpm_data) == 0x03u &&
            io->read8(io->context, rpm_data + 1u) == 0x3au &&
            io->read8(io->context, coolant_data) == 0x09u &&
            io->read8(io->context, coolant_data + 1u) == 0x38u) {
            io->write8(io->context, rpm_control, CAN_SLOT_RR);
            io->write8(io->context, coolant_control, CAN_SLOT_RR);
            armed = (io->read8(io->context, rpm_control) & CAN_SLOT_RR) != 0u &&
                    (io->read8(io->context, coolant_control) & CAN_SLOT_RR) != 0u &&
                    can0_available(io);
            if (!armed) {
                io->write8(io->context, rpm_control, 0u);
                io->write8(io->context, coolant_control, 0u);
            }
        }
    }
    io->leave(io->context, saved_state);
    return armed;
}

static Lfj8CanResult write_if_idle(const Lfj8RegisterIo *io, uint16_t id,
                                  const uint8_t payload[8])
{
    uint8_t control;
    uint32_t i;

    if (!can0_available(io)) {
        return LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    }
    if ((io->read16(io->context, LFJ8_CAN0_EXTID) & LFJ8_CAN0_EXTID_IDE13) != 0u) {
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

Lfj8CanResult lfj8_h03_can0_diag_submit(const Lfj8RegisterIo *io, const uint8_t payload[8])
{
    const uint32_t saved_state = io->enter(io->context);
    const Lfj8CanResult result = h03_can0_operational(io) ?
        write_if_idle(io, LFJ8_CAN_DIAG_REPLY, payload) : LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    io->leave(io->context, saved_state);
    return result;
}

static Lfj8CanTxStatus slot13_status(const Lfj8RegisterIo *io, uint16_t expected_id,
                                    uint8_t cancel, uint16_t *finished_at)
{
    if (!h03_can0_operational(io) ||
        (io->read16(io->context, LFJ8_CAN0_EXTID) & LFJ8_CAN0_EXTID_IDE13) != 0u) {
        return LFJ8_CAN_TX_UNAVAILABLE;
    }
    const uint8_t control = io->read8(io->context, LFJ8_CAN0_SLOT13_CNT);
    if (control == 0u) {
        return LFJ8_CAN_TX_IDLE;
    }
    if ((control & (uint8_t)~(CAN_SLOT_TR | CAN_SLOT_TRSTAT | CAN_SLOT_TRFIN)) != 0u) {
        return LFJ8_CAN_TX_UNAVAILABLE;
    }
    if ((control & (CAN_SLOT_TRFIN | CAN_SLOT_TRSTAT)) == CAN_SLOT_TRFIN) {
        if (io->read8(io->context, LFJ8_CAN0_SLOT13_SID0) != (expected_id >> 6) ||
            io->read8(io->context, LFJ8_CAN0_SLOT13_SID1) != (expected_id & 0x3fu)) {
            return LFJ8_CAN_TX_UNAVAILABLE;
        }
        *finished_at = io->read16(io->context, LFJ8_CAN0_SLOT13_TIMESTAMP);
        return h03_can0_operational(io) ? LFJ8_CAN_TX_FINISHED : LFJ8_CAN_TX_UNAVAILABLE;
    }
    if (cancel && (control & CAN_SLOT_TR) != 0u && h03_can0_operational(io)) {
        /* A frame already on the wire can finish. Do not reuse this slot
         * until a later poll observes idle or completion. */
        io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, CAN_SLOT_ABORT_TX);
    }
    return LFJ8_CAN_TX_PENDING;
}

Lfj8CanTxStatus lfj8_h03_can0_diag_status(const Lfj8RegisterIo *io, uint8_t cancel,
                                       uint16_t *finished_at)
{
    const uint32_t saved_state = io->enter(io->context);
    const Lfj8CanTxStatus result = slot13_status(io, LFJ8_CAN_DIAG_REPLY, cancel, finished_at);
    io->leave(io->context, saved_state);
    return result;
}

static int h03_can0_tx13_polling(const Lfj8RegisterIo *io)
{
    return (io->read16(io->context, LFJ8_CAN0_SLIMK) & LFJ8_CAN0_SLIMK_TX13) == 0u;
}

static Lfj8CanResult torque_slot_available(const Lfj8RegisterIo *io)
{
    if (!h03_can0_tx13_polling(io)) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    if (!h03_can0_operational(io)) {
        return LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    }
    if ((io->read16(io->context, LFJ8_CAN0_EXTID) & LFJ8_CAN0_EXTID_IDE13) != 0u) {
        return LFJ8_CAN_SLOT_NOT_STANDARD;
    }
    return LFJ8_CAN_READY;
}

static int torque_listener_id(const Lfj8RegisterIo *io)
{
    return io->read8(io->context, LFJ8_CAN0_SLOT13_SID0) == (LFJ8_CAN_TORQUE_STATUS >> 6) &&
           io->read8(io->context, LFJ8_CAN0_SLOT13_SID1) == (LFJ8_CAN_TORQUE_STATUS & 0x3fu);
}

static Lfj8CanResult pause_torque_listener(const Lfj8RegisterIo *io)
{
    const uint8_t control = io->read8(io->context, LFJ8_CAN0_SLOT13_CNT);
    if (control == 0u || control == CAN_SLOT_TRFIN || control == (CAN_SLOT_TR | CAN_SLOT_TRFIN)) {
        return LFJ8_CAN_READY;
    }
    if ((control & (uint8_t)~(CAN_SLOT_RR | CAN_SLOT_TRFIN | CAN_SLOT_ML)) != 0u ||
        (control & CAN_SLOT_RR) == 0u) {
        return LFJ8_CAN_SLOT_BUSY;
    }
    /* RR can start receiving asynchronously. Stop the leased listener
     * and verify idle before another sender touches the message storage. */
    io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, 0u);
    return io->read8(io->context, LFJ8_CAN0_SLOT13_CNT) == 0u ? LFJ8_CAN_READY : LFJ8_CAN_SLOT_BUSY;
}

static Lfj8CanResult listen_for_torque_status(const Lfj8RegisterIo *io)
{
    if (io->read8(io->context, LFJ8_CAN0_GMSKS0) != 0x1fu ||
        io->read8(io->context, LFJ8_CAN0_GMSKS1) != 0x3fu) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    const uint8_t control = io->read8(io->context, LFJ8_CAN0_SLOT13_CNT);
    if ((control & CAN_SLOT_RR) != 0u) {
        return (control & CAN_SLOT_TRSTAT) != 0u ? LFJ8_CAN_SLOT_BUSY : LFJ8_CAN_READY;
    }
    if (control != 0u && control != CAN_SLOT_TRFIN && control != (CAN_SLOT_TR | CAN_SLOT_TRFIN)) {
        return LFJ8_CAN_SLOT_BUSY;
    }
    io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, 0u);
    if (io->read8(io->context, LFJ8_CAN0_SLOT13_CNT) != 0u) {
        return LFJ8_CAN_SLOT_BUSY;
    }
    io->write8(io->context, LFJ8_CAN0_SLOT13_SID0, (uint8_t)(LFJ8_CAN_TORQUE_STATUS >> 6));
    io->write8(io->context, LFJ8_CAN0_SLOT13_SID1, (uint8_t)(LFJ8_CAN_TORQUE_STATUS & 0x3fu));
    io->write8(io->context, LFJ8_CAN0_SLOT13_DLC, 8u);
    if (!h03_can0_operational(io) || !torque_listener_id(io)) {
        return LFJ8_CAN_CONTROLLER_UNAVAILABLE;
    }
    io->write8(io->context, LFJ8_CAN0_SLOT13_CNT, CAN_SLOT_RR);
    return (io->read8(io->context, LFJ8_CAN0_SLOT13_CNT) & CAN_SLOT_RR) != 0u ?
        LFJ8_CAN_READY : LFJ8_CAN_CONTROLLER_UNAVAILABLE;
}

Lfj8CanResult lfj8_h03_can0_torque_listen(const Lfj8RegisterIo *io, uint8_t tx13_owned)
{
    if (tx13_owned != 1u) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    const uint32_t saved_state = io->enter(io->context);
    Lfj8CanResult result = torque_slot_available(io);
    if (result == LFJ8_CAN_READY) {
        result = listen_for_torque_status(io);
    }
    io->leave(io->context, saved_state);
    return result;
}

Lfj8CanRxResult lfj8_h03_can0_torque_receive(const Lfj8RegisterIo *io, uint8_t tx13_owned,
                                           Lfj8CanData8 *frame)
{
    if (tx13_owned != 1u) {
        return LFJ8_CAN_RX_WRONG_SLOT;
    }
    const uint32_t saved_state = io->enter(io->context);
    Lfj8CanRxResult result = LFJ8_CAN_RX_UNAVAILABLE;
    if (torque_slot_available(io) == LFJ8_CAN_READY) {
        result = receive8(io, 13u, frame);
        if (result == LFJ8_CAN_RX_RECEIVED && frame->id != LFJ8_CAN_TORQUE_STATUS) {
            result = LFJ8_CAN_RX_WRONG_SLOT;
        }
    }
    io->leave(io->context, saved_state);
    return result;
}

Lfj8CanResult lfj8_h03_can0_torque_yield(const Lfj8RegisterIo *io, uint8_t tx13_owned)
{
    if (tx13_owned != 1u) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    const uint32_t saved_state = io->enter(io->context);
    Lfj8CanResult result = torque_slot_available(io);
    if (result == LFJ8_CAN_READY) {
        result = pause_torque_listener(io);
    }
    io->leave(io->context, saved_state);
    return result;
}

Lfj8CanResult lfj8_h03_can0_torque_submit(const Lfj8RegisterIo *io, uint8_t tx13_owned,
                                       const uint8_t payload[8])
{
    if (tx13_owned != 1u) {
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    const uint32_t saved_state = io->enter(io->context);
    Lfj8CanResult result = torque_slot_available(io);
    if (result == LFJ8_CAN_READY) {
        result = pause_torque_listener(io);
        if (result == LFJ8_CAN_READY) {
            result = write_if_idle(io, LFJ8_CAN_TORQUE_REQUEST, payload);
        }
    }
    io->leave(io->context, saved_state);
    return result;
}

Lfj8CanTxStatus lfj8_h03_can0_torque_status(const Lfj8RegisterIo *io, uint8_t tx13_owned,
                                         uint8_t cancel, uint16_t *finished_at)
{
    if (tx13_owned != 1u) {
        return LFJ8_CAN_TX_UNAVAILABLE;
    }
    const uint32_t saved_state = io->enter(io->context);
    const Lfj8CanTxStatus result = h03_can0_tx13_polling(io) ?
        slot13_status(io, LFJ8_CAN_TORQUE_REQUEST, cancel, finished_at) : LFJ8_CAN_TX_UNAVAILABLE;
    io->leave(io->context, saved_state);
    return result;
}

int lfj8_h03_can0_epoch_drained(const Lfj8RegisterIo *io)
{
    if (torque_slot_available(io) != LFJ8_CAN_READY ||
        (io->read16(io->context, LFJ8_CAN0_STAT) & CAN_STAT_BASIC) == 0u) {
        return 0;
    }
    const uint8_t tx = io->read8(io->context, LFJ8_CAN0_SLOT13_CNT);
    /* A completed OEM TX can retain TR. There is no project submission
     * until the broker enters the new generation and replaces the slot. */
    return (tx == 0u || tx == CAN_SLOT_TRFIN || tx == (CAN_SLOT_TR | CAN_SLOT_TRFIN)) &&
           io->read8(io->context, LFJ8_CAN0_SLOT_CNT + 14u) == CAN_SLOT_RR &&
           io->read8(io->context, LFJ8_CAN0_SLOT_CNT + 15u) == CAN_SLOT_RR &&
           (io->read16(io->context, LFJ8_CAN0_SLIST) & LFJ8_CAN0_BASIC_RX_BITS) == 0u &&
           h03_can0_operational(io);
}

int lfj8_h03_can0_slot13_timestamp(const Lfj8RegisterIo *io, uint16_t *timestamp)
{
    const uint32_t saved_state = io->enter(io->context);
    const int available = torque_slot_available(io) == LFJ8_CAN_READY;
    *timestamp = available ? io->read16(io->context, LFJ8_CAN0_TSTMP) : 0u;
    io->leave(io->context, saved_state);
    return available;
}

Lfj8CanTxStatus lfj8_h03_can0_telemetry_status(const Lfj8RegisterIo *io,
                                            uint16_t id, uint8_t cancel)
{
    if (id != LFJ8_CAN_1AE && id != LFJ8_CAN_300) {
        return LFJ8_CAN_TX_UNAVAILABLE;
    }
    uint16_t finished_at;
    const uint32_t saved_state = io->enter(io->context);
    const Lfj8CanTxStatus result = h03_can0_tx13_polling(io) ?
        slot13_status(io, id, cancel, &finished_at) : LFJ8_CAN_TX_UNAVAILABLE;
    io->leave(io->context, saved_state);
    return result;
}
