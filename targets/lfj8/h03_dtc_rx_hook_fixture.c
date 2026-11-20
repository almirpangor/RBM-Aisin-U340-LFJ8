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
