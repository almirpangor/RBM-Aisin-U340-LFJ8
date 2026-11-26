#include "lfj8_bridge.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

volatile Lfj8H03Atf rbm_h03_atf_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
Lfj8H03SensorTarget rbm_h03_sensor_state;
const Lfj8H03SensorFeedConfig rbm_h03_sensor_config = {300u, 300u, 300u, 0u};

#ifdef SENSOR_APPLICATION_GATE
#include "lfj8_h03_application.h"

Lfj8H03Application rbm_h03_application;
static int fixture_ram_owned;

static int owns_ram(void *context)
{
    (void)context;
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    assert(!(psw & 0x40u));
    return fixture_ram_owned;
}

static const Lfj8H03TakeoverOps takeover_ops = {.io = &lfj8_h03_mmio};
const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &takeover_ops,
    .ram_owned = owns_ram,
};
#else
int lfj8_h03_application_running_locked(void)
{
    return 1; /* Standalone store and clock tests use an admitted application. */
}
#endif

int fixture_s51(uint32_t captured);
int fixture_s83(uint32_t captured);

#ifdef SENSOR_STOCK
#define S51_BUNDLE ".long 0x2244f000\n"
#define S83_BUNDLE ".long 0x2045f000\n"
#else
#define S51_BUNDLE "bra.l rbm_h03_s51_capture_hook\n"
#define S83_BUNDLE "bra.l rbm_h03_s83_capture_hook\n"
#endif

/* Execute each replacement at its original address. The local continuation
 * compares PSW and the input value, then returns to the C fixture. */
__asm__(
    ".text\n"
    ".p2align 2\n"
    ".global fixture_s51\n"
    "fixture_s51:\n"
    "mv r2,r0\n"
    "ld24 r4,#0x8048b8\n"
    "mvfc r6,psw\n"
    "bra.l fixture_s51_site\n"
    ".p2align 2\n"
    ".global fixture_s83\n"
    "fixture_s83:\n"
    "mv r2,r0\n"
    "ld24 r5,#0x8048bc\n"
    "mvfc r6,psw\n"
    "bra.l fixture_s83_site\n"
    ".section .sensor_s51,\"ax\",@progbits\n"
    ".global fixture_s51_site\n"
    "fixture_s51_site:\n"
    S51_BUNDLE
    ".global h03_sensor_after_s51\n"
    "h03_sensor_after_s51:\n"
    "mvfc r7,psw\n"
    "xor r7,r6\n"
    "xor r0,r2\n"
    "or r0,r7\n"
    "jmp lr\n"
    ".section .sensor_s83,\"ax\",@progbits\n"
    ".global fixture_s83_site\n"
    "fixture_s83_site:\n"
    S83_BUNDLE
    ".global h03_sensor_after_s83\n"
    "h03_sensor_after_s83:\n"
    "mvfc r7,psw\n"
    "xor r7,r6\n"
    "xor r0,r2\n"
    "or r0,r7\n"
    "jmp lr\n"
    ".text\n"
);

#define MMIO8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define MMIO16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define MMIO32(address) (*(volatile uint32_t *)(uintptr_t)(address))

#ifdef SENSOR_APPLICATION_GATE
static void verify_inputs_stay_closed(void)
{
    /* A bad live register would clear retained state if a gate were checked late. */
    MMIO8(0x800FEB) = 0x30;
    rbm_h03_tml0_1mhz_qualified = 1u;
    rbm_h03_sensor_state.feed.epoch = 19u;
    rbm_h03_sensor_state.feed.epoch_seen = 1u;
    rbm_h03_atf_state = (Lfj8H03Atf){
        .last_adc_us = 10u, .adc = 315u, .adc_seen = 1u, .pending_adc = 1u, .valid = 1u,
    };
    MMIO16(0x804BC4) = 317u;
    Lfj8H03AtfSample old = {.acquired_us = 101u, .atf_c = 60, .toyota_gp_m7184 = 300u};
    assert(!lfj8_h03_atf_target_snapshot(300u, &old));
    assert(!old.acquired_us && !old.atf_c && !old.toyota_gp_m7184);
    uint32_t acquired = UINT32_MAX;
    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    rbm_h03_atf_adc_callback();
    assert(!rbm_h03_atf_source_callback(315u, &acquired) && acquired == UINT32_MAX);
    rbm_h03_atf_publish_callback(LFJ8_H03_ATF_DIRECT_STORE, &acquired);
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);
    assert(!fixture_s51(77u) && !fixture_s83(99u));
    assert(MMIO32(0x8048B8) == 77u && MMIO32(0x8048BC) == 99u);
    assert(rbm_h03_tml0_1mhz_qualified && rbm_h03_sensor_state.feed.epoch == 19u);
    assert(rbm_h03_sensor_state.feed.epoch_seen && !rbm_h03_sensor_state.s51.primed);
    assert(!rbm_h03_sensor_state.s83.primed);
    assert(rbm_h03_atf_state.last_adc_us == 10u && rbm_h03_atf_state.adc == 315u);
    assert(rbm_h03_atf_state.pending_adc && rbm_h03_atf_state.valid);
}
#endif

int main(void)
{
    MMIO8(0x800203) = 9;
    MMIO8(0x8003EB) = 0x01;
#ifdef SENSOR_APPLICATION_GATE
    rbm_h03_application.running = 1u; /* Stale running flag without ownership. */
    verify_inputs_stay_closed();
    fixture_ram_owned = 1;
    rbm_h03_application.running = 0u;
    verify_inputs_stay_closed();
    rbm_h03_sensor_state.feed.epoch = 0u;
    rbm_h03_application.running = 1u;
    puts("H03 input lifecycle: unowned RAM and stopped application PASS");
#endif
    MMIO8(0x800FEB) = 0x31;
    assert(rbm_h03_sensor_clock_rebase(1));

    __asm__ volatile ("clrpsw #0x40" ::: "memory", "cc");
    assert(!fixture_s51(UINT32_MAX - 140u));
    assert(!fixture_s83(790));
    __asm__ volatile ("setpsw #0x40" ::: "memory", "cc");
    assert(!fixture_s51(UINT32_MAX - 40u));
    assert(!fixture_s83(890));
    assert(MMIO32(0x8048B8) == UINT32_MAX - 40u && MMIO32(0x8048BC) == 890u);

#ifdef SENSOR_STOCK
    assert(!rbm_h03_sensor_state.s51.primed && !rbm_h03_sensor_state.s83.primed);
    puts("H03 stock S51/S83 stores and PSW PASS");
#else
    MMIO8(0x8063E7) = 0;
    MMIO16(0x804BC4) = 315;
    MMIO32(0x804F04) = UINT32_C(0x3FC4E000);
    MMIO32(0x805028) = UINT32_C(0x42700000);
    MMIO32(0x8003E0) = UINT32_MAX - 30u;
    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    rbm_h03_atf_adc_callback();
    uint32_t acquired;
    assert(rbm_h03_atf_source_callback(315, &acquired));
    MMIO32(0x8003E0) = UINT32_MAX - 1u;
    rbm_h03_atf_publish_callback(LFJ8_H03_ATF_DIRECT_STORE, &acquired);
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);

    MMIO32(0x8003E0) = 1;
    MMIO32(0x800FE0) = 1000;
    Lfj8H03SensorSnapshot snapshot;
    assert(rbm_h03_sensor_foreground(0, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.epoch == 1u && snapshot.capture.now_tml0 == 1u);
    assert(snapshot.capture.vss.state == LFJ8_VSS_VALID && snapshot.capture.vss.interval_ticks == 100u);
    assert(snapshot.capture.nt.state == LFJ8_VSS_VALID && snapshot.capture.nt.interval_ticks == 100u);
    assert(snapshot.capture.nt_at_tml0 == 1u - 110u);
    assert(snapshot.atf_valid && snapshot.atf.atf_c == 60 && snapshot.atf.acquired_us == acquired);

    Lfj8H03AtfSample atf;
    MMIO8(0x800FEB) = 0x30;
    assert(!lfj8_h03_atf_target_snapshot(300u, &atf));
    assert(!rbm_h03_tml0_1mhz_qualified && !rbm_h03_atf_state.valid);

    /* Restore the register before either capture hook or foreground sees the change. */
    MMIO8(0x800FEB) = 0x31;
    uint32_t now_us = 0x12345678u;
    assert(!rbm_h03_atf_now_us(&now_us) && now_us == 0x12345678u);
    assert(!fixture_s51(2) && MMIO32(0x8048B8) == 2);
    assert(!rbm_h03_sensor_state.s51.primed && !rbm_h03_sensor_state.s83.primed);
    assert(rbm_h03_sensor_foreground(1, &snapshot) == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    MMIO8(0x800FEB) = 0x30;
    assert(!rbm_h03_sensor_clock_rebase(1));
    MMIO8(0x800FEB) = 0x31;
    assert(rbm_h03_sensor_clock_rebase(1));
    assert(rbm_h03_sensor_foreground(0, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.epoch == 4u && snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE && !snapshot.atf_valid);

    /* Correct control registers alone must not hide a stalled TML1. */
    assert(!fixture_s51(10u) && !fixture_s83(1002u));
    rbm_h03_atf_state.valid = 1u;
    MMIO32(0x8003E0) += 8u;
    assert(rbm_h03_sensor_foreground(1, &snapshot) == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    assert(!rbm_h03_tml0_1mhz_qualified && !rbm_h03_atf_state.valid);
    assert(!rbm_h03_sensor_state.s51.primed && !rbm_h03_sensor_state.s83.primed);
    assert(!snapshot.epoch && !snapshot.atf_valid && snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);
    MMIO32(0x800FE0) += 8u;
    assert(rbm_h03_sensor_foreground(0, &snapshot) == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    assert(rbm_h03_sensor_clock_rebase(1));
    assert(rbm_h03_sensor_foreground(0, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);

    MMIO8(0x8003EB) = 0x11; /* Bit 0 still selects Clock Bus 1. */
    assert(!rbm_h03_atf_now_us(&now_us) && !rbm_h03_tml0_1mhz_qualified);
    MMIO8(0x8003EB) = 0x01;
    assert(!rbm_h03_atf_now_us(&now_us));
    assert(!rbm_h03_sensor_clock_rebase(0));

    puts("H03 sensors: native stores, common clock revocation and new epoch PASS");
#endif
    return 0;
}
