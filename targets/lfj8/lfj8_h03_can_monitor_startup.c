#include "lfj8_h03_can_monitor_startup.h"
#include "lfj8_h03_mmio.h"

#include <stdbool.h>

#define CAN0 UINT32_C(0x801000)
#define CAN1 UINT32_C(0x801400)
#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_FELBANK0 UINT32_C(0x8007E8)
#define H03_FELBANK1 UINT32_C(0x8007EA)
#define H03_FESBANK0 UINT32_C(0x8007F0)
#define H03_FESBANK1 UINT32_C(0x8007F2)
#define H03_MONITOR_FLAGS UINT32_C(0x808580)
#define H03_SUM_REMAINING UINT32_C(0x808DA4)
#define H03_COPY_REMAINING UINT32_C(0x808DA8)
#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_PROGRAMMING_GATE UINT32_C(0x80801C)

enum {
    CAN_STAT = 2, CAN_SLIST = 0x0c, CAN_MSC14 = 0x5e, CAN_MSC15 = 0x5f,
    CAN_RST = 1, CAN_BCM = 8, CAN_FRST = 16, CAN_CRS = 0x0100,
    CAN_BOS = 0x4000, CAN_RX = 0x40, BASIC_PENDING = 3,
    BANK_ENABLE = 0x8000, SERVICE_OPEN = 0x20, SERVICE_CLOSED = 0x10,
    RESET_READ_LIMIT = 16384,
};

#ifndef RBM_H03_MONITOR_STARTUP_SIMULATOR
static void write_halfword(void *context, uint32_t address, uint16_t value)
{
    (void)context;
    *(volatile uint16_t *)(uintptr_t)address = value;
}

static void write_word(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    *(volatile uint32_t *)(uintptr_t)address = value;
}

const Lfj8H03MonitorIo rbm_h03_can_monitor_io = {
    .io = &lfj8_h03_mmio,
    .write16 = write_halfword,
    .write32 = write_word,
};
#endif

static const Lfj8H03MonitorIo *const monitor = &rbm_h03_can_monitor_io;

static int normal_flash(void)
{
    const Lfj8RegisterIo *const io = monitor->io;
    return io->read8(io->context, H03_FCNT1) == 0u &&
        io->read8(io->context, H03_SERVICE_MODE) != 4u &&
        io->read8(io->context, H03_PROGRAMMING_GATE) == 0u;
}

static void request_reset(uint32_t base)
{
    const Lfj8RegisterIo *const io = monitor->io;
    const uint16_t cnt = io->read16(io->context, base);
    const uint16_t stat = io->read16(io->context, base + CAN_STAT);
    const unsigned reset = stat & CAN_BOS ? CAN_FRST : CAN_RST;
    monitor->write16(io->context, base, (uint16_t)(cnt | reset));
}

static int await_reset(uint32_t base, unsigned expected)
{
    const Lfj8RegisterIo *const io = monitor->io;
    for (unsigned reads = 0; reads < RESET_READ_LIMIT; ++reads) {
        if ((io->read16(io->context, base + CAN_STAT) & CAN_CRS) == expected) {
            return 1;
        }
    }
    return 0;
}

static void discard_basiccan(uint32_t base)
{
    const Lfj8RegisterIo *const io = monitor->io;
    void *const context = io->context;
    io->write8(context, base + CAN_MSC14, 0u);
    io->write8(context, base + CAN_MSC15, 0u);
    /* SLIST clears selected flags with a zero; all other flags are kept. */
    monitor->write16(context, base + CAN_SLIST, (uint16_t)~BASIC_PENDING);
}

static void arm_basiccan(uint32_t base)
{
    const Lfj8RegisterIo *const io = monitor->io;
    io->write8(io->context, base + CAN_MSC14, CAN_RX);
    io->write8(io->context, base + CAN_MSC15, CAN_RX);
}

static int basiccan_armed_behind_reset(uint32_t base)
{
    const Lfj8RegisterIo *const io = monitor->io;
    void *const context = io->context;
    return (io->read16(context, base + CAN_STAT) & CAN_CRS) &&
        io->read8(context, base + CAN_MSC14) == CAN_RX &&
        io->read8(context, base + CAN_MSC15) == CAN_RX &&
        !(io->read16(context, base + CAN_SLIST) & BASIC_PENDING);
}

static int discard_monitor_work(void)
{
    const Lfj8RegisterIo *const io = monitor->io;
    void *const context = io->context;
    if ((io->read16(context, H03_FELBANK0) | io->read16(context, H03_FELBANK1) |
         io->read16(context, H03_FESBANK0)) & BANK_ENABLE) {
        return 0;
    }

    const uint16_t select = io->read16(context, H03_FESBANK1);
    if (select & BANK_ENABLE) {
        monitor->write16(context, H03_FESBANK1, (uint16_t)(select & ~BANK_ENABLE));
    }
    monitor->write32(context, H03_SUM_REMAINING, 0u);
    monitor->write32(context, H03_COPY_REMAINING, 0u);
    const uint8_t flags = io->read8(context, H03_MONITOR_FLAGS);
    if (flags & SERVICE_OPEN) {
        io->write8(context, H03_MONITOR_FLAGS, (uint8_t)((flags & ~SERVICE_OPEN) | SERVICE_CLOSED));
    }
    return !(io->read16(context, H03_FESBANK1) & BANK_ENABLE) &&
        !(io->read8(context, H03_MONITOR_FLAGS) & SERVICE_OPEN) &&
        !io->read32(context, H03_SUM_REMAINING) && !io->read32(context, H03_COPY_REMAINING);
}

static int park_pair(void)
{
    request_reset(CAN0);
    request_reset(CAN1);
    if (!await_reset(CAN0, CAN_CRS) || !await_reset(CAN1, CAN_CRS)) {
        return 0;
    }
    discard_basiccan(CAN0);
    discard_basiccan(CAN1);
    return discard_monitor_work();
}

static int rearm_locked(uint16_t can0_control, bool cold)
{
    if (!normal_flash()) {
        return 0;
    }
    const Lfj8RegisterIo *const io = monitor->io;
    void *const context = io->context;
    const uint16_t can1_control = io->read16(context, CAN1);

    if (!park_pair() || !lfj8_h03_monitor_configure_filters_locked(io)) {
        return 0;
    }

    arm_basiccan(CAN0);
    arm_basiccan(CAN1);
    if (!basiccan_armed_behind_reset(CAN0) || !basiccan_armed_behind_reset(CAN1)) {
        return 0;
    }
    if (cold && !rbm_h03_can_monitor_cold_owner_init_locked()) {
        return 0;
    }

    /* The filters are already locked by RR before either controller can
     * receive a frame. Old ADC0 work was discarded while both were parked. */
    monitor->write16(context, CAN0, (uint16_t)((can0_control | CAN_BCM) & ~(CAN_RST | CAN_FRST)));
    monitor->write16(context, CAN1, (uint16_t)((can1_control | CAN_BCM) & ~(CAN_RST | CAN_FRST)));
    if (await_reset(CAN0, 0u) && await_reset(CAN1, 0u) &&
        lfj8_h03_monitor_isolated_locked(io)) {
        return 1;
    }

    request_reset(CAN0);
    request_reset(CAN1);
    return 0;
}

int rbm_h03_can_monitor_rearm(void)
{
    const Lfj8RegisterIo *const io = monitor->io;
    const uint32_t saved = io->enter(io->context);
    const int ready = rearm_locked(io->read16(io->context, CAN0), true);
    io->leave(io->context, saved);
    return ready;
}

int rbm_h03_can_monitor_runtime_rearm(void)
{
    const Lfj8RegisterIo *const io = monitor->io;
    const uint32_t saved = io->enter(io->context);
    rbm_h03_can_monitor_revoke_locked();
    const int ready = rearm_locked(CAN_BCM, false);
    if (ready) {
        rbm_h03_can_monitor_publish_setup_locked();
    }
    io->leave(io->context, saved);
    return ready;
}

int rbm_h03_can_monitor_prepare_recovery(void)
{
    /* The original 00B85C lock remains held across this call and the parked
     * native setup. The later permit hook owns the actual receive release. */
    rbm_h03_can_monitor_revoke_locked();
    return normal_flash() && park_pair();
}
