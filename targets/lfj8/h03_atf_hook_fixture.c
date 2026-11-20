/* Simulator providers for the H03 ATF callback ABI. */
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"

int lfj8_h03_application_running_locked(void)
{
    return 1; /* Standalone ATF probe runs with the application admitted. */
}

volatile Lfj8H03Atf rbm_h03_atf_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
volatile uint32_t atf_fixture_adc_us = 100;
volatile uint32_t atf_fixture_publish_us = 102;
volatile uint32_t atf_fixture_clock_fail;
volatile uint32_t atf_fixture_irq_enabled;
volatile uint32_t atf_fixture_acquisitions;
volatile uint32_t atf_fixture_reads;
volatile uint32_t atf_fixture_site;
volatile uint32_t atf_fixture_source;
volatile int atf_fixture_valid;
volatile uint32_t atf_fixture_sample_us;
volatile uint16_t atf_fixture_q8;

static uint32_t clock_stage;
static uint32_t clock_us;

static uint32_t read_psw(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    return psw;
}

int __real_rbm_h03_atf_now_us(uint32_t *now_us);

int __wrap_rbm_h03_atf_now_us(uint32_t *now_us)
{
    atf_fixture_irq_enabled |= read_psw() & 0x40u;
    const uint32_t failure = atf_fixture_clock_fail & clock_stage;
    if (failure == 1u) {
        rbm_h03_tml0_1mhz_qualified = 0u;
    }
    *(volatile uint8_t *)0x800203 = failure == 2u ? 8u : 9u;
    *(volatile uint8_t *)0x8003EB = failure == 4u ? 0u : 1u;
    *(volatile uint8_t *)0x800FEB = 0x31u;
    *(volatile uint32_t *)0x8003E0 = clock_us;
    return __real_rbm_h03_atf_now_us(now_us);
}

void __real_rbm_h03_atf_adc_callback(void);
int __real_rbm_h03_atf_source_callback(uint16_t raw, uint32_t *acquired_us);
void __real_rbm_h03_atf_publish_callback(uint32_t site, const uint32_t *acquired_us);

void __wrap_rbm_h03_atf_adc_callback(void)
{
    if (!clock_stage) {
        rbm_h03_tml0_1mhz_qualified = 1u;
    }
    clock_stage = 1u;
    clock_us = atf_fixture_adc_us;
    __real_rbm_h03_atf_adc_callback();
    atf_fixture_acquisitions += rbm_h03_atf_state.adc_seen;
}

int __wrap_rbm_h03_atf_source_callback(uint16_t raw, uint32_t *acquired_us)
{
    atf_fixture_irq_enabled |= read_psw() & 0x40u;
    ++atf_fixture_reads;
    return __real_rbm_h03_atf_source_callback(raw, acquired_us);
}

void __wrap_rbm_h03_atf_publish_callback(uint32_t site, const uint32_t *acquired_us)
{
    clock_stage = 2u;
    clock_us = atf_fixture_publish_us;
    atf_fixture_site = site;
    atf_fixture_source = acquired_us ? *acquired_us : UINT32_MAX;
    __real_rbm_h03_atf_publish_callback(site, acquired_us);
}

void atf_fixture_observe(void)
{
    clock_stage = 4u;
    clock_us = atf_fixture_publish_us;
    Lfj8H03AtfSample sample = {.acquired_us = UINT32_MAX, .toyota_gp_m7184 = UINT16_MAX};
    atf_fixture_valid = lfj8_h03_atf_target_snapshot(20u, &sample);
    atf_fixture_q8 = sample.toyota_gp_m7184;
    atf_fixture_sample_us = sample.acquired_us;
    if (!(read_psw() & 0x40u)) {
        atf_fixture_irq_enabled |= 1u; /* Snapshot failed to restore foreground IE. */
    }
    if (atf_fixture_clock_fail & 4u) {
        atf_fixture_clock_fail = 0;
        if (lfj8_h03_atf_target_snapshot(20u, &sample)) {
            atf_fixture_irq_enabled |= 2u; /* Old reading reappeared after clock recovery. */
        }
    }
}
