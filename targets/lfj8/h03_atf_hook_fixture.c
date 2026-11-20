/* Simulator providers for the H03 ATF callback ABI. */
#include "lfj8_h03_atf.h"

static Lfj8H03Atf atf;
volatile uint32_t atf_fixture_adc_us = 100;
volatile uint32_t atf_fixture_publish_us = 102;
volatile uint32_t atf_fixture_irq_enabled;
volatile uint32_t atf_fixture_acquisitions;
volatile uint32_t atf_fixture_reads;
volatile uint32_t atf_fixture_site;
volatile uint32_t atf_fixture_source;
volatile int atf_fixture_valid;
volatile uint32_t atf_fixture_sample_us;
volatile uint16_t atf_fixture_q8;

static uint32_t check_irq_disabled(void *unused)
{
    (void)unused;
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    atf_fixture_irq_enabled |= psw & 0x40u;
    return psw;
}

static void leave(void *unused, uint32_t saved)
{
    (void)saved;
    (void)check_irq_disabled(unused);
}

static uint8_t byte(void *unused, uint32_t address)
{
    (void)unused;
    return *(volatile const uint8_t *)(uintptr_t)address;
}

static uint16_t halfword(void *unused, uint32_t address)
{
    (void)unused;
    return *(volatile const uint16_t *)(uintptr_t)address;
}

static uint32_t word(void *unused, uint32_t address)
{
    (void)unused;
    return *(volatile const uint32_t *)(uintptr_t)address;
}

static const Lfj8RegisterIo io = {
    .read8 = byte, .read16 = halfword, .read32 = word,
    .enter = check_irq_disabled, .leave = leave,
};

void rbm_h03_atf_adc_callback(void)
{
    (void)check_irq_disabled(0);
    atf_fixture_acquisitions += lfj8_h03_atf_after_adc_store(&atf, &io, atf_fixture_adc_us);
}

int rbm_h03_atf_source_callback(uint16_t raw, uint32_t *acquired_us)
{
    (void)check_irq_disabled(0);
    ++atf_fixture_reads;
    return lfj8_h03_atf_capture_source(&atf, raw, acquired_us);
}

void rbm_h03_atf_publish_callback(uint32_t site, const uint32_t *acquired_us)
{
    (void)check_irq_disabled(0);
    atf_fixture_site = site;
    atf_fixture_source = acquired_us ? *acquired_us : UINT32_MAX;
    if (lfj8_h03_atf_after_store(&atf, &io, site, acquired_us, atf_fixture_publish_us)) {
        Lfj8H03AtfSample sample;
        atf_fixture_valid = lfj8_h03_atf_snapshot(&atf, &io, atf_fixture_publish_us, 20u, &sample);
        atf_fixture_q8 = sample.toyota_gp_m7184;
        atf_fixture_sample_us = sample.acquired_us;
    }
}
