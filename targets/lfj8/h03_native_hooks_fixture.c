#include <stdint.h>

#include "h03_native_hooks.h"

#define RAM8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define RAM32(address) (*(volatile uint32_t *)(uintptr_t)(address))

volatile int fixture_decision;
volatile int fixture_commit_site;
volatile unsigned fixture_strategy_calls;
volatile unsigned fixture_commit_calls;

static int decide(volatile unsigned *calls)
{
    ++*calls;
    __asm__ volatile (
        "ldi r5,#1\n\t"
        "mvtaclo r5\n\t"
        "mvtachi r5\n\t"
        "cmpu r5,r5"
        ::: "r5", "a0", "cbit");
    return fixture_decision;
}

int rbm_h03_strategy_callback(void)
{
    int decision = decide(&fixture_strategy_calls);
    if (decision == RBM_H03_HOOK_OEM) {
        RAM8(0x8063d5) = 1;
        RAM8(0x8063d8) = 0;
        RAM8(0x8063db) = 1;
        RAM32(0x80508c) = 0x3f000000;
    }
    return decision;
}

int rbm_h03_commit_callback(void)
{
    return decide(&fixture_commit_calls);
}
