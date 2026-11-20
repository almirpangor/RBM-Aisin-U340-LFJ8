#ifdef RBM_DTC_RX_TARGET_FIXTURE

#include "lfj8_h03_dtc_target.h"
#include "lfj8_h03_mmio.h"
#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
#include "lfj8_h03_can_owner.h"
#endif

Lfj8H03DtcTarget fixture_target;
Lfj8H03Can13Result fixture_foreground_result;
uint32_t fixture_rx_high_probe;
static Lfj8H03Can13 broker;
static CheryDtcState dtc;

#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
static Lfj8H03CanOwner owner;

static bool rx_epoch(void *context, uint32_t *generation)
{
    return lfj8_h03_can_owner_rx_epoch(context, generation);
}

static Lfj8H03Can13Result poll_owner(void *context, Lfj8H03Can13 *can13, Lfj8H03DtcRxQueue *queue,
                                     const Lfj8RegisterIo *io, Lfj8H03Can13Input *input,
                                     const uint16_t *can_now, bool native_ready)
{
    return lfj8_h03_can_owner_poll(context, can13, queue, io, input, can_now, native_ready);
}

static void owner_setup_completed(void)
{
    lfj8_h03_can_owner_init(&owner);
    owner.setup_generation = 7; /* The model supplies the native setup notification. */
}
#else
static uint32_t owner;

static bool rx_epoch(void *context, uint32_t *generation)
{
    *generation = *(const uint32_t *)context;
    return true;
}

static Lfj8H03Can13Result poll_owner(void *context, Lfj8H03Can13 *can13, Lfj8H03DtcRxQueue *queue,
                                     const Lfj8RegisterIo *io, Lfj8H03Can13Input *input,
                                     const uint16_t *can_now, bool native_ready)
{
    input->generation = *(const uint32_t *)context;
    input->owns_slot13 = native_ready;
    lfj8_h03_dtc_rx_queue_reset(queue, io, input->generation);
    return lfj8_h03_dtc_foreground_poll(can13, queue, io, input, can_now);
}

static void owner_setup_completed(void)
{
    owner = 7;
}
#endif

static const Lfj8H03DtcCanOwnerOps owner_ops = {rx_epoch, poll_owner, &owner};

void fixture_rx_init(void)
{
    const Lfj8H03Can13Config config = {
        .torque_receive_age_bits = 4000, .diagnostic_receive_age_bits = 1024,
        .max_poll_gap_us = 5000, .bit_time_us = 2,
    };
    lfj8_h03_dtc_target_unbind();
    chery_dtc_init(&dtc);
    if (lfj8_h03_can13_init(&broker, &config, 0) &&
        lfj8_h03_dtc_target_init(&fixture_target, &broker, &lfj8_h03_mmio, &owner_ops,
                                lfj8_h03_tml0ct_m32r, 4)) {
        owner_setup_completed();
    }
}

void fixture_rx_foreground(void)
{
    Lfj8H03Can13Input input = {.diagnostic_tick = 10, .owns_slot13 = 1, .dtc = &dtc};
    fixture_foreground_result = lfj8_h03_dtc_target_poll(&fixture_target, &input, true);
}

#else

#include "lfj8_h03_dtc_rx_queue.h"

Lfj8H03DtcRxQueue fixture_rx_queue;
uint32_t fixture_rx_calls;
uint32_t fixture_rx_irq_enabled;
uint32_t fixture_rx_high_probe;
#ifdef RBM_DTC_RX_DISPATCH_FIXTURE
uint32_t fixture_rx_begins;
uint32_t fixture_rx_paired_mask;
uint32_t fixture_rx_skips;
static Lfj8H03DtcRxDispatch fixture_dispatch;
#endif

static uint8_t read_byte(void *context, uint32_t address)
{
    (void)context;
    return *(volatile const uint8_t *)(uintptr_t)address;
}

static uint16_t read_halfword(void *context, uint32_t address)
{
    (void)context;
    return *(volatile const uint16_t *)(uintptr_t)address;
}

static uint32_t enter(void *context)
{
    (void)context;
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    fixture_rx_irq_enabled += (psw & 0x40u) != 0u;
    return psw;
}

static void leave(void *context, uint32_t saved)
{
    (void)context;
    (void)saved;
    __asm__ volatile ("" : : : "memory");
}

static const Lfj8RegisterIo fixture_io = {
    .read8 = read_byte, .read16 = read_halfword, .enter = enter, .leave = leave,
};

void fixture_rx_init(void)
{
    lfj8_h03_dtc_rx_queue_init(&fixture_rx_queue, 7, 1024, 2);
}

static inline void clobber_context(uint32_t entry_psw)
{
    const uint32_t clobber = UINT32_C(0x00123456);
    const uint32_t toggled_psw = entry_psw ^ UINT32_C(1);
    __asm__ volatile ("mvtaclo %0\n\tmvtachi %0\n\tmvtc %1,psw"
                      : : "r"(clobber), "r"(toggled_psw) : "cc");
}

#ifdef RBM_DTC_RX_DISPATCH_FIXTURE
void rbm_h03_dtc_rx_begin(uint16_t pending)
{
    uint32_t entry_psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(entry_psw) : : "memory");
    ++fixture_rx_begins;
    fixture_rx_paired_mask = lfj8_h03_dtc_rx_dispatch_begin(
        &fixture_dispatch, &fixture_rx_queue, &fixture_io, pending, 7, 5000, 0x1400);
    clobber_context(entry_psw);
}
#endif

void rbm_h03_dtc_rx_observe(uint8_t slot)
{
    uint32_t entry_psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(entry_psw) : : "memory");
    ++fixture_rx_calls;
#ifdef RBM_DTC_RX_DISPATCH_FIXTURE
    if (lfj8_h03_dtc_rx_dispatch_skip_paired(&fixture_dispatch, slot, 7)) {
        ++fixture_rx_skips;
    } else
#endif
    {
        /* Synthetic paired clocks for the scripted slot timestamps. */
        lfj8_h03_dtc_rx_queue_capture_basic(&fixture_rx_queue, &fixture_io, slot, 7, 5000, 0x1400);
    }
    /* Exercise the wrapper's accumulator and condition-bit restore. */
    clobber_context(entry_psw);
}

#endif
