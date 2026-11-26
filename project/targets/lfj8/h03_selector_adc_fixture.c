/* Instrumentation for the target callback. The simulator supplies clock and RAM. */
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"

volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
volatile uint32_t selector_fixture_captured_us;
volatile uint8_t selector_fixture_clock_available;
volatile uint8_t selector_fixture_application_running;
volatile unsigned selector_fixture_clock_reads;
volatile uint32_t selector_fixture_calls;
volatile uint32_t selector_fixture_psw;
volatile uint32_t selector_fixture_callback_sp;
volatile uint16_t selector_fixture_argument;
volatile uint16_t selector_fixture_stock_word;
volatile uint16_t selector_fixture_an3_before;

/* Measure SP before the C prologue. A debugger breakpoint would mask IE. */
__asm__ (
    ".section .text.selector_fixture_entry,\"ax\",@progbits\n"
    ".p2align 2\n"
    ".global __wrap_rbm_h03_selector_adc_capture\n"
    "__wrap_rbm_h03_selector_adc_capture:\n"
    "ld24 r1,#selector_fixture_callback_sp\n"
    "st sp,@r1\n"
    "bra selector_fixture_capture\n"
    ".previous\n"
);

int lfj8_h03_application_running_locked(void)
{
    return selector_fixture_application_running;
}

int rbm_h03_atf_now_us(uint32_t *now_us)
{
    ++selector_fixture_clock_reads;
    if (!selector_fixture_clock_available) {
        return 0;
    }
    *now_us = selector_fixture_captured_us;
    return 1;
}

void __real_rbm_h03_selector_adc_capture(uint16_t raw);

void selector_fixture_capture(uint16_t raw)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    selector_fixture_psw = psw;
    ++selector_fixture_calls;
    selector_fixture_argument = raw;
    selector_fixture_stock_word = lfj8_h03_mmio.read16(0, 0x804bc6u);
    selector_fixture_an3_before = lfj8_h03_mmio.read16(0, 0x804bc0u);
    __real_rbm_h03_selector_adc_capture(raw);

    /* Deliberately change ACC and the condition bit before returning. */
    __asm__ volatile ("ldi %0,#0x3141\n\tmvtachi %0\n\tmvtaclo %0\n\tmvfc %0,psw\n\t"
                      "xor3 %0,%0,#1\n\tmvtc %0,psw"
                      : "=&r"(psw) : : "cc", "memory");
}
