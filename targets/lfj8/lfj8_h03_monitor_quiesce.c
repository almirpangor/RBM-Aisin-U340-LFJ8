#include "lfj8_h03_monitor_quiesce.h"

#define CAN0_BASE UINT32_C(0x801000)
#define CAN1_BASE UINT32_C(0x801400)
#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_FELBANK0 UINT32_C(0x8007E8)
#define H03_FELBANK1 UINT32_C(0x8007EA)
#define H03_FESBANK0 UINT32_C(0x8007F0)
#define H03_FESBANK1 UINT32_C(0x8007F2)
#define H03_SESSION_FLAGS UINT32_C(0x808580)
#define H03_PROGRAMMING_GATE UINT32_C(0x80801C)
#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_SUM_REMAINING UINT32_C(0x808DA4)
#define H03_COPY_REMAINING UINT32_C(0x808DA8)

enum {
    CAN_STAT = 0x02, CAN_EXTID = 0x04, CAN_LOCAL_A = 0x30, CAN_LOCAL_B = 0x38,
    CAN_MSC14 = 0x5e, CAN_MSC15 = 0x5f, CAN_SID14 = 0x1e0, CAN_SID15 = 0x1f0,
    CAN_BCS = 0x0800, CAN_CRS = 0x0100, CAN_BASIC_IDE_BITS = 0x0003,
    CAN_DIAG_SID_HIGH = 0x700 >> 6, CAN_RX_REQUEST = 0x40,
    CAN_TX_REQUEST = 0x80, CAN_TRFIN = 0x01,
    FLASH_FEMMOD = 0x01, FLASH_BANK_ENABLE = 0x8000,
    SERVICE_OPEN = 0x20, SERVICE_CLOSED = 0x10,
};

static int stored_filters(const Lfj8RegisterIo *io, uint32_t base)
{
    void *const context = io->context;
    return io->read8(context, base + CAN_LOCAL_A) == CAN_DIAG_SID_HIGH &&
        io->read8(context, base + CAN_LOCAL_A + 1u) == 0u &&
        io->read8(context, base + CAN_LOCAL_B) == CAN_DIAG_SID_HIGH &&
        io->read8(context, base + CAN_LOCAL_B + 1u) == 0u &&
        (io->read8(context, base + CAN_SID14) & CAN_DIAG_SID_HIGH) == CAN_DIAG_SID_HIGH &&
        (io->read8(context, base + CAN_SID15) & CAN_DIAG_SID_HIGH) == CAN_DIAG_SID_HIGH;
}

static int controller_stopped(const Lfj8RegisterIo *io, uint32_t base)
{
    void *const context = io->context;
    return (io->read16(context, base + CAN_STAT) & CAN_CRS) &&
        !(io->read16(context, base + CAN_EXTID) & CAN_BASIC_IDE_BITS) &&
        !((io->read8(context, base + CAN_MSC14) |
           io->read8(context, base + CAN_MSC15)) & (CAN_TX_REQUEST | CAN_RX_REQUEST | CAN_TRFIN));
}

static void set_filters(const Lfj8RegisterIo *io, uint32_t base)
{
    const uint32_t fields[] = {CAN_LOCAL_A, CAN_LOCAL_B, CAN_SID14, CAN_SID15};
    for (unsigned field = 0; field < sizeof fields / sizeof fields[0]; ++field) {
        io->write8(io->context, base + fields[field], CAN_DIAG_SID_HIGH);
        io->write8(io->context, base + fields[field] + 1u, 0u);
    }
}

int lfj8_h03_monitor_configure_filters_locked(const Lfj8RegisterIo *io)
{
    if (!io || !io->read8 || !io->read16 || !io->write8 ||
        !controller_stopped(io, CAN0_BASE) || !controller_stopped(io, CAN1_BASE)) {
        return 0;
    }
    set_filters(io, CAN0_BASE);
    set_filters(io, CAN1_BASE);
    return stored_filters(io, CAN0_BASE) && stored_filters(io, CAN1_BASE);
}

static int channel_filters(const Lfj8RegisterIo *io, uint32_t base)
{
    void *const context = io->context;
    const unsigned requests = CAN_RX_REQUEST | CAN_TX_REQUEST;
    return (io->read16(context, base + CAN_STAT) & (CAN_BCS | CAN_CRS)) == CAN_BCS &&
        !(io->read16(context, base + CAN_EXTID) & CAN_BASIC_IDE_BITS) &&
        (io->read8(context, base + CAN_MSC14) & requests) == CAN_RX_REQUEST &&
        (io->read8(context, base + CAN_MSC15) & requests) == CAN_RX_REQUEST &&
        stored_filters(io, base);
}

int lfj8_h03_monitor_filters_locked(const Lfj8RegisterIo *io)
{
    return io && io->read8 && io->read16 &&
        channel_filters(io, CAN0_BASE) && channel_filters(io, CAN1_BASE);
}

static int slots_empty(const Lfj8RegisterIo *io, uint32_t base)
{
    void *const context = io->context;
    return !((io->read8(context, base + CAN_MSC14) |
              io->read8(context, base + CAN_MSC15)) & CAN_TRFIN);
}

static int other_banks_disabled(const Lfj8RegisterIo *io)
{
    void *const context = io->context;
    return !((io->read16(context, H03_FELBANK0) |
              io->read16(context, H03_FELBANK1) |
              io->read16(context, H03_FESBANK0)) & FLASH_BANK_ENABLE);
}

static int working_mode(const Lfj8RegisterIo *io)
{
    return io->read8(io->context, H03_PROGRAMMING_GATE) == 0u &&
        io->read8(io->context, H03_SERVICE_MODE) != 4u;
}

int lfj8_h03_monitor_isolated_locked(const Lfj8RegisterIo *io)
{
    if (!lfj8_h03_monitor_filters_locked(io) || !io->read32) {
        return 0;
    }
    void *const context = io->context;
    return working_mode(io) && other_banks_disabled(io) && !io->read8(context, H03_FCNT1) &&
        !(io->read16(context, H03_FESBANK1) & FLASH_BANK_ENABLE) &&
        !(io->read8(context, H03_SESSION_FLAGS) & SERVICE_OPEN) &&
        !io->read32(context, H03_SUM_REMAINING) && !io->read32(context, H03_COPY_REMAINING);
}

int lfj8_h03_monitor_quiesce(const Lfj8H03MonitorIo *monitor)
{
    const Lfj8RegisterIo *const io = monitor ? monitor->io : 0;
    if (!io || !io->read8 || !io->read16 || !io->read32 || !io->write8 ||
        !io->enter || !io->leave || !monitor->write16 || !monitor->write32) {
        return 0;
    }

    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    int ready = 0;
    if (lfj8_h03_monitor_filters_locked(io) &&
        slots_empty(io, CAN0_BASE) && slots_empty(io, CAN1_BASE) &&
        working_mode(io) && other_banks_disabled(io) &&
        !(io->read8(context, H03_FCNT1) & ~FLASH_FEMMOD)) {
        /* Match the order of the stock 003594 disable branch. Do not enter
         * E/W mode or alter the selected bank number. */
        const uint16_t bank = io->read16(context, H03_FESBANK1);
        monitor->write16(context, H03_FESBANK1, (uint16_t)(bank & ~FLASH_BANK_ENABLE));
        io->write8(context, H03_FCNT1, 0u);
        /* The known ADC0 worker examines these counters independently of
         * session flags. Clear both under the same exclusion. */
        monitor->write32(context, H03_SUM_REMAINING, 0u);
        monitor->write32(context, H03_COPY_REMAINING, 0u);
        const uint8_t flags = io->read8(context, H03_SESSION_FLAGS);
        if (flags & SERVICE_OPEN) {
            io->write8(context, H03_SESSION_FLAGS, (uint8_t)((flags & ~SERVICE_OPEN) | SERVICE_CLOSED));
        }
        ready = lfj8_h03_monitor_isolated_locked(io);
    }
    io->leave(context, saved);
    return ready;
}
