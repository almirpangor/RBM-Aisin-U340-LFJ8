#include "lfj8_h03_ram_owner.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_storage.h"

#define H03_APPLICATION_START UINT32_C(0x008000)
#define H03_FLASH_END UINT32_C(0x080000)
#define H03_RAM_START UINT32_C(0x804000)
#define H03_RAM_END UINT32_C(0x80A000)
#define H03_SPI_START UINT32_C(0x809EFC)
#define H03_PSW_CURSOR UINT32_C(0x809F9C)
#define H03_SBI_SPI_BYTES UINT32_C(40)
#define H03_SBI_PSW_BYTES UINT32_C(4)
#define H03_PSW_IE_OR_SM UINT32_C(0xC0)
#define H03_MONITOR_FIRST UINT32_C(0x808578)
#define H03_MONITOR_END UINT32_C(0x808DB4)

#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_FELBANK0 UINT32_C(0x8007E8)
#define H03_FELBANK1 UINT32_C(0x8007EA)
#define H03_FESBANK0 UINT32_C(0x8007F0)
#define H03_FESBANK1 UINT32_C(0x8007F2)
#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_PROGRAMMING_GATE UINT32_C(0x80801C)

#define H03_DIRECT_SITE UINT32_C(0x002924)
#define H03_SPAN_SITE UINT32_C(0x00294C)
#define H03_COPY_SITE UINT32_C(0x002D1C)
#define H03_CLOSE_SITE UINT32_C(0x002E9C)
#define H03_VIRTUAL_SITE UINT32_C(0x003568)
#define H03_VIRTUAL_DISABLE UINT32_C(0x003594)
#define LONG_BRA UINT32_C(0xFF000000)
#define LONG_BL UINT32_C(0xFE000000)
#define LD24_R0 UINT32_C(0xE0000000)
#define LOW_24_BITS UINT32_C(0x00FFFFFF)

static int in_application_flash(uintptr_t address, uint32_t bytes)
{
    return !(address & 3u) && address >= H03_APPLICATION_START &&
           address <= H03_FLASH_END - bytes;
}

static uint32_t read_word(uint32_t address)
{
    return lfj8_h03_mmio.read32(lfj8_h03_mmio.context, address);
}

static int has_stack_room(Lfj8H03ServiceRange bounds, uint32_t current,
                          uint32_t top, uint32_t reserve)
{
    return !(current & 3u) && current <= top && current <= bounds.end &&
           current >= bounds.first && current - bounds.first >= reserve;
}

static int live_stacks_ready(const Lfj8H03RamOwner *owner)
{
    uint32_t psw;
    uint32_t spi;
    __asm__ volatile ("mvfc %0,psw\n\tmvfc %1,cr2"
                      : "=r"(psw), "=r"(spi) : : "memory");
    if ((psw & H03_PSW_IE_OR_SM) ||
        (owner->spi_reserve_bytes | owner->psw_reserve_bytes) & 3u ||
        owner->spi_reserve_bytes < H03_SBI_SPI_BYTES ||
        owner->psw_reserve_bytes < H03_SBI_PSW_BYTES ||
        !has_stack_room(owner->spi, spi, H03_SPI_START, owner->spi_reserve_bytes)) {
        return 0;
    }
    return has_stack_room(owner->psw, read_word(H03_PSW_CURSOR), H03_PSW_CURSOR,
                          owner->psw_reserve_bytes);
}

static int plain_flash(void)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    void *const context = io->context;
    return io->read8(context, H03_FCNT1) == 0u &&
           io->read8(context, H03_SERVICE_MODE) != 4u &&
           io->read8(context, H03_PROGRAMMING_GATE) == 0u &&
           !((io->read16(context, H03_FELBANK0) | io->read16(context, H03_FELBANK1) |
              io->read16(context, H03_FESBANK0) | io->read16(context, H03_FESBANK1)) & 0x8000u);
}

static int branch_matches(uint32_t at, uint32_t target, uint32_t opcode)
{
    return read_word(at) == (opcode | (((target - at) >> 2) & LOW_24_BITS));
}

static const Lfj8H03ServicePolicy *installed_policy(const Lfj8H03RamOwner *owner)
{
    if (!in_application_flash(owner->direct_hook, 4u) ||
        !in_application_flash(owner->span_hook, 0x24u) ||
        !in_application_flash(owner->copy_hook, 0x30u) ||
        !in_application_flash(owner->close_hook, 0x30u) ||
        !branch_matches(H03_DIRECT_SITE, owner->direct_hook, LONG_BRA) ||
        !branch_matches(H03_SPAN_SITE, owner->span_hook, LONG_BL) ||
        !branch_matches(H03_COPY_SITE, owner->copy_hook, LONG_BRA) ||
        !branch_matches(H03_CLOSE_SITE, owner->close_hook, LONG_BRA) ||
        !branch_matches(H03_VIRTUAL_SITE, H03_VIRTUAL_DISABLE, LONG_BRA)) {
        return 0;
    }

    /* Relocations in h03_service_guard_hooks.S load the same immutable policy
     * at these offsets. Verify the following calls against the linked guards. */
    const uint32_t policy_load = read_word(owner->span_hook + 0x1cu);
    const uint32_t address = policy_load & LOW_24_BITS;
    if (policy_load != (LD24_R0 | address) ||
        !in_application_flash(address, sizeof(Lfj8H03ServicePolicy)) ||
        read_word(owner->copy_hook + 0x18u) != policy_load ||
        read_word(owner->close_hook + 0x20u) != policy_load ||
        !branch_matches(owner->span_hook + 0x20u,
                       (uint32_t)(uintptr_t)&lfj8_h03_service_span_allowed, LONG_BL) ||
        !branch_matches(owner->copy_hook + 0x2cu,
                       (uint32_t)(uintptr_t)&lfj8_h03_service_copy_allowed, LONG_BL) ||
        !branch_matches(owner->close_hook + 0x2cu,
                       (uint32_t)(uintptr_t)&lfj8_h03_service_copy_allowed, LONG_BL)) {
        return 0;
    }
    return (const Lfj8H03ServicePolicy *)(uintptr_t)address;
}

static int covers(const Lfj8H03ServicePolicy *policy, Lfj8H03ServiceRange required)
{
    for (uint32_t i = 0; i < policy->count; ++i) {
        const Lfj8H03ServiceRange range = policy->ranges[i];
        if (range.end <= required.first) {
            continue;
        }
        if (range.first > required.first) {
            return 0;
        }
        if (range.end >= required.end) {
            return 1;
        }
        required.first = range.end;
    }
    return 0;
}

static int qualified_layout(const Lfj8H03RamOwner *owner, const Lfj8H03ServicePolicy *policy)
{
    const Lfj8H03ServiceRange monitor = {H03_MONITOR_FIRST, H03_MONITOR_END};
    const Lfj8H03ServiceRange *const required[] = {
        &owner->control, &owner->communication, &owner->workspace, &owner->dtc_irq_pointer,
        &monitor, &owner->spi, &owner->psw,
    };
    if (!lfj8_h03_service_span_allowed(policy, 0u, 0u) ||
        owner->spi.first >= H03_SPI_START || owner->spi.end < H03_SPI_START ||
        owner->psw.first >= H03_PSW_CURSOR || owner->psw.end <= H03_PSW_CURSOR) {
        return 0;
    }
    for (unsigned i = 0; i < sizeof required / sizeof required[0]; ++i) {
        const Lfj8H03ServiceRange span = *required[i];
        if (span.first < H03_RAM_START || span.end > H03_RAM_END || span.first >= span.end ||
            ((span.first | span.end) & 3u) || !covers(policy, span)) {
            return 0;
        }
        for (unsigned earlier = 0; earlier < i; ++earlier) {
            if (span.first < required[earlier]->end && required[earlier]->first < span.end) {
                return 0;
            }
        }
    }
    return owner->control.end - owner->control.first >= sizeof(Lfj8H03ControlStorage) &&
           owner->communication.end - owner->communication.first >= sizeof(Lfj8H03CommunicationStorage) &&
           owner->workspace.end - owner->workspace.first >= sizeof(Lfj8H03WorkspaceStorage) &&
           owner->dtc_irq_pointer.end - owner->dtc_irq_pointer.first == sizeof(void *);
}

int lfj8_h03_ram_owned(void *context)
{
    const Lfj8H03RamOwner *const owner = context;
    if (!in_application_flash((uintptr_t)owner, sizeof *owner) ||
        !owner->boot_and_other_writers_owned || !plain_flash() || !live_stacks_ready(owner) ||
        owner->boot_and_other_writers_owned(owner->platform) != 1) {
        return 0;
    }
    return qualified_layout(owner, installed_policy(owner));
}
