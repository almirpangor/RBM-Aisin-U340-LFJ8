#include "lfj8_h03_mmio.h"
#include "lfj8_h03_ram_owner.h"
#include "lfj8_h03_storage.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

#define BYTE(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define HALF(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define WORD(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define OWNER_ADDRESS 0x31000u
#define POLICY_ADDRESS 0x30000u
#define CONTROL_ADDRESS 0x806b40u
#define COMM_ADDRESS 0x808e40u
#define IRQ_ADDRESS 0x8094c0u
#define OWNER (*(Lfj8H03RamOwner *)(uintptr_t)OWNER_ADDRESS)
#define POLICY (*(Lfj8H03ServicePolicy *)(uintptr_t)POLICY_ADDRESS)

void rbm_h03_service_direct_hook(void);
void rbm_h03_service_span_hook(void);
void rbm_h03_service_copy_hook(void);
void rbm_h03_service_close_hook(void);

Lfj8H03Application rbm_h03_application;
static Lfj8RegisterIo application_io;
static Lfj8H03Takeover takeover;
static Lfj8H03MainResult result;
static RbmU340eRuntime runtime;
static unsigned inhibit_count;
static unsigned rebase_count;
static int platform_owned;
static uint32_t entry_spi = 0x809efcu;

void fixture_cold_gate(uint32_t spi);

__asm__(
    ".text\n.p2align 2\n"
    ".global fixture_cold_gate\n"
    "fixture_cold_gate:\n"
    "mvfc r2,psw\n"
    "clrpsw #0x80\n"
    "mvfc r3,cr2\n"
    "mv sp,r0\n"
    "push r3\n"
    "push r2\n"
    "push lr\n"
    "bl.l rbm_h03_application_cold_gate\n"
    "pop lr\n"
    "pop r2\n"
    "pop r3\n"
    "mvtc r3,cr2\n"
    "mvtc r2,psw\n"
    "jmp lr\n"
);

static const uint32_t sites[] = {0x2924u, 0x294cu, 0x2d1cu, 0x2e9cu, 0x3568u};
static const uint32_t original[] = {ROM_DIRECT, ROM_SPAN, ROM_COPY, ROM_CLOSE, ROM_VIRTUAL};

static int irq_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    return (psw & 0x40u) != 0u;
}

static int boot_ready(void *platform)
{
    assert(!irq_enabled() && platform == &platform_owned);
    return platform_owned;
}

static void inhibit(void *platform)
{
    assert(!irq_enabled() && platform == &OWNER);
    inhibit_count++;
}

int rbm_h03_sensor_clock_rebase(uint8_t physical_1mhz)
{
    assert(!irq_enabled() && !physical_1mhz);
    rebase_count++;
    return 0;
}

static const Lfj8H03TakeoverOps ops = {.io = &application_io, .inhibit = inhibit};
const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &ops, .takeover = &takeover, .main = &result, .runtime = &runtime,
    .ram_owned = lfj8_h03_ram_owned,
};

static void require_cold_gate(int accepted)
{
    rbm_h03_application.running = 1u;
    takeover.pending = 1u;
    takeover.ops = &ops;
    result.valid = 1u;
    runtime.initialized = 1u;
    inhibit_count = 0u;
    rebase_count = 0u;
    fixture_cold_gate(entry_spi);
    assert(irq_enabled());
    assert(rbm_h03_application.running == !accepted && takeover.pending == !accepted &&
           takeover.ops == (accepted ? NULL : &ops) && result.valid == !accepted &&
           runtime.initialized == !accepted && inhibit_count == (unsigned)accepted &&
           rebase_count == (unsigned)accepted);
}

static uint32_t branch(uint32_t from, uint32_t to, uint32_t opcode)
{
    return opcode | (((to - from) >> 2) & UINT32_C(0x00ffffff));
}

static void fixture_map(void)
{
    const uint32_t workspace = COMM_ADDRESS + sizeof(Lfj8H03CommunicationStorage);
    OWNER = (Lfj8H03RamOwner){
        .control = {CONTROL_ADDRESS, CONTROL_ADDRESS + sizeof(Lfj8H03ControlStorage)},
        .communication = {COMM_ADDRESS, workspace},
        .workspace = {workspace, workspace + sizeof(Lfj8H03WorkspaceStorage)},
        .dtc_irq_pointer = {IRQ_ADDRESS, IRQ_ADDRESS + 4u},
        .spi = {0x809700u, 0x809efcu}, .psw = {0x809f00u, 0x809fa0u},
        .spi_reserve_bytes = 0x100u, .psw_reserve_bytes = 8u,
        .direct_hook = (uint32_t)(uintptr_t)&rbm_h03_service_direct_hook,
        .span_hook = (uint32_t)(uintptr_t)&rbm_h03_service_span_hook,
        .copy_hook = (uint32_t)(uintptr_t)&rbm_h03_service_copy_hook,
        .close_hook = (uint32_t)(uintptr_t)&rbm_h03_service_close_hook,
        .platform = &platform_owned, .boot_and_other_writers_owned = boot_ready,
    };
    WORD(0x809f9cu) = 0x809f9cu;
    POLICY = (Lfj8H03ServicePolicy){
        .count = 4u,
        .ranges = {{CONTROL_ADDRESS, OWNER.control.end}, {0x808578u, 0x808db4u},
                   {COMM_ADDRESS, IRQ_ADDRESS + 4u}, {OWNER.spi.first, OWNER.psw.end}},
    };
}

int main(void)
{
    __asm__ volatile ("setpsw #0x40" ::: "memory", "cc");
    application_io = lfj8_h03_mmio;
    application_io.context = &OWNER;
    platform_owned = 1;
    fixture_map();
    for (unsigned i = 0; i < sizeof sites / sizeof sites[0]; ++i) {
        WORD(sites[i]) = original[i];
    }
    require_cold_gate(0);

    const uint32_t patched[] = {
        branch(sites[0], OWNER.direct_hook, UINT32_C(0xff000000)),
        branch(sites[1], OWNER.span_hook, UINT32_C(0xfe000000)),
        branch(sites[2], OWNER.copy_hook, UINT32_C(0xff000000)),
        branch(sites[3], OWNER.close_hook, UINT32_C(0xff000000)),
        branch(sites[4], 0x003594u, UINT32_C(0xff000000)),
    };
    for (unsigned i = 0; i < sizeof sites / sizeof sites[0]; ++i) {
        WORD(sites[i]) = patched[i];
    }
    require_cold_gate(1);

    for (unsigned i = 0; i < sizeof sites / sizeof sites[0]; ++i) {
        WORD(sites[i]) = original[i];
        require_cold_gate(0);
        WORD(sites[i]) = patched[i];
    }
    const uint32_t copy_load = OWNER.copy_hook + 0x18u;
    const uint32_t original_load = WORD(copy_load);
    WORD(copy_load) = original_load + 4u;
    require_cold_gate(0);
    WORD(copy_load) = original_load;
    const uint32_t span_call = OWNER.span_hook + 0x20u;
    const uint32_t original_call = WORD(span_call);
    WORD(span_call) = original_call + 1u;
    require_cold_gate(0);
    WORD(span_call) = original_call;

    const uint32_t flash_banks[] = {0x8007e8u, 0x8007eau, 0x8007f0u, 0x8007f2u};
    for (unsigned i = 0; i < sizeof flash_banks / sizeof flash_banks[0]; ++i) {
        HALF(flash_banks[i]) = 0x8000u;
        require_cold_gate(0);
        HALF(flash_banks[i]) = 0u;
    }
    BYTE(0x8007e2u) = 1u;
    require_cold_gate(0);
    BYTE(0x8007e2u) = 0u;
    BYTE(0x804887u) = 4u;
    require_cold_gate(0);
    BYTE(0x804887u) = 0u;
    BYTE(0x80801cu) = 1u;
    require_cold_gate(0);
    BYTE(0x80801cu) = 0u;

    POLICY.ranges[0].end -= 4u;
    require_cold_gate(0);
    fixture_map();
    POLICY.ranges[1].first += 4u;
    require_cold_gate(0);
    fixture_map();
    POLICY.ranges[2].end -= 4u;
    require_cold_gate(0);
    fixture_map();
    POLICY.ranges[3].end -= 4u;
    require_cold_gate(0);
    fixture_map();
    POLICY.ranges[4] = POLICY.ranges[3];
    POLICY.ranges[3].end = OWNER.spi.end - 4u;
    POLICY.ranges[4].first = OWNER.spi.end - 4u;
    POLICY.count = 5u;
    require_cold_gate(1); /* Adjacent pieces are continuous. */
    POLICY.ranges[4].first += 8u;
    require_cold_gate(0);
    fixture_map();
    POLICY.count = LFJ8_H03_SERVICE_RANGES + 1u;
    require_cold_gate(0);
    fixture_map();
    OWNER.control.end -= 4u;
    require_cold_gate(0);
    fixture_map();
    OWNER.dtc_irq_pointer.first = OWNER.workspace.first;
    OWNER.dtc_irq_pointer.end = OWNER.workspace.first + 4u;
    require_cold_gate(0);
    fixture_map();
    OWNER.psw.end = 0x809f9cu;
    require_cold_gate(0);
    fixture_map();

    platform_owned = 0;
    require_cold_gate(0);
    platform_owned = 1;
    OWNER.boot_and_other_writers_owned = NULL;
    require_cold_gate(0);
    fixture_map();
    application_io.context = (void *)(uintptr_t)CONTROL_ADDRESS;
    require_cold_gate(0);
    application_io.context = &OWNER;
    HALF(0x801002u) = 0x0100u; /* CAN0/1 still parked. */
    HALF(0x801402u) = 0x0100u;
    require_cold_gate(1);
    entry_spi = 0x809780u;
    require_cold_gate(0);
    entry_spi = 0x809efcu;
    OWNER.spi_reserve_bytes = 36u;
    require_cold_gate(0);
    fixture_map();
    OWNER.spi_reserve_bytes += 1u;
    require_cold_gate(0);
    fixture_map();
    WORD(0x809f9cu) = 0x809fa0u;
    require_cold_gate(0);
    WORD(0x809f9cu) = 0x809f09u;
    require_cold_gate(0);
    WORD(0x809f9cu) = 0x809f04u;
    require_cold_gate(0);
    WORD(0x809f9cu) = 0x809f08u;
    require_cold_gate(1); /* Exact remaining PSW reserve. */
    OWNER.psw_reserve_bytes = 0u;
    require_cold_gate(0);
    fixture_map();
    require_cold_gate(1);
    puts("H03 RAM owner: cold gate, native service words and live stacks PASS");
    return 0;
}
