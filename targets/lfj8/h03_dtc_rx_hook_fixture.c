#ifdef RBM_DTC_RX_TARGET_FIXTURE

#include "lfj8_h03_dtc_target.h"
#include "lfj8_h03_mmio.h"
#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_dtc_native.h"

Lfj8H03CanOwner h03_can_owner;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
uint8_t fixture_native_bound;
volatile uint8_t fixture_rebind;
volatile uint8_t fixture_t6_action;
uint8_t fixture_t6_started;
uint32_t fixture_t6_initial;
Lfj8H03DtcT6Config fixture_t6_config;
Lfj8H03DtcT6Clock fixture_t6_clock;
#endif

Lfj8H03DtcTarget fixture_target;
Lfj8H03Can13Result fixture_foreground_result;
uint32_t fixture_rx_high_probe;
static Lfj8H03Can13 broker;
static CheryDtcState dtc;

#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
/* Qualify the actual native register check in simulator-backed MMIO. */
static void fixture_qualify_clock(void)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    io->write8(io->context, 0x800203, 9);
    io->write8(io->context, 0x8003eb, 1);
    io->write8(io->context, 0x800feb, 0x31);
    rbm_h03_tml0_1mhz_qualified = 1u;
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
static const Lfj8H03DtcCanOwnerOps owner_ops = {rx_epoch, poll_owner, &owner};
#endif

void fixture_rx_init(void)
{
    const Lfj8H03Can13Config config = {
        .torque_receive_age_bits = 4000, .diagnostic_receive_age_bits = 1024,
        .max_poll_gap_us = 5000, .bit_time_us = 2,
    };
    chery_dtc_init(&dtc);
    if (!lfj8_h03_can13_init(&broker, &config, 0)) {
        return;
    }
#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
    lfj8_h03_dtc_native_cold_init();
    if (lfj8_h03_dtc_native_bind(&fixture_target, &broker, 4)) {
        /* Clock qualification must precede the IRQ binding. */
        return;
    }
    h03_can_owner.setup_generation = 7; /* The model supplies the setup notification. */
    fixture_qualify_clock();
    fixture_native_bound = lfj8_h03_dtc_native_bind(&fixture_target, &broker, 4);
    fixture_t6_config = (Lfj8H03DtcT6Config){5, 2, 1000}; /* Arbitrary model units. */
#else
    lfj8_h03_dtc_target_unbind();
    if (lfj8_h03_dtc_target_init(&fixture_target, &broker, &lfj8_h03_mmio, &owner_ops,
                                lfj8_h03_tml0ct_m32r, 4)) {
        owner_setup_completed();
    }
#endif
}

void fixture_rx_foreground(void)
{
    Lfj8H03Can13Input input = {.diagnostic_tick = 10, .owns_slot13 = 1, .dtc = &dtc};
#ifdef RBM_DTC_RX_CAN_OWNER_FIXTURE
    if (fixture_rebind) {
        fixture_rebind = 0u;
        lfj8_h03_dtc_native_unbind();
        fixture_native_bound = lfj8_h03_dtc_native_bind(&fixture_target, &broker, 4);
    }
    if (fixture_t6_action == 1u) {
        fixture_t6_started = lfj8_h03_dtc_native_start_t6(
            &fixture_t6_clock, &fixture_t6_config, fixture_t6_initial);
        fixture_t6_action = 2u;
    }
    fixture_foreground_result = fixture_t6_action
        ? lfj8_h03_dtc_native_poll_t6(&fixture_target, &input, true, &fixture_t6_clock)
        : lfj8_h03_dtc_native_poll(&fixture_target, &input, true);
#else
    fixture_foreground_result = lfj8_h03_dtc_target_poll(&fixture_target, &input, true);
#endif
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
