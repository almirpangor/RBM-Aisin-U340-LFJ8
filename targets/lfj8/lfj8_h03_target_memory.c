#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_ram_owner.h"

/* Absolute symbols from the final image linker script, never read as RAM. */
#define DECLARE_RANGE(name) \
    extern const uint8_t rbm_h03_ram_##name##_first[], rbm_h03_ram_##name##_end[]
#define ADDRESS(symbol) ((uint32_t)(uintptr_t)(symbol))
#define RANGE(name) {ADDRESS(rbm_h03_ram_##name##_first), ADDRESS(rbm_h03_ram_##name##_end)}

DECLARE_RANGE(control);
DECLARE_RANGE(communication);
DECLARE_RANGE(workspace);
DECLARE_RANGE(dtc_irq_pointer);
DECLARE_RANGE(spi);
DECLARE_RANGE(psw);
extern const uint8_t rbm_h03_ram_spi_reserve[], rbm_h03_ram_psw_reserve[];

void rbm_h03_service_direct_hook(void);
void rbm_h03_service_span_hook(void);
void rbm_h03_service_copy_hook(void);
void rbm_h03_service_close_hook(void);

static const Lfj8H03RamOwner target_owner = {
    .control = RANGE(control),
    .communication = RANGE(communication),
    .workspace = RANGE(workspace),
    .dtc_irq_pointer = RANGE(dtc_irq_pointer),
    .spi = RANGE(spi),
    .psw = RANGE(psw),
    .spi_reserve_bytes = ADDRESS(rbm_h03_ram_spi_reserve),
    .psw_reserve_bytes = ADDRESS(rbm_h03_ram_psw_reserve),
    .direct_hook = ADDRESS(rbm_h03_service_direct_hook),
    .span_hook = ADDRESS(rbm_h03_service_span_hook),
    .copy_hook = ADDRESS(rbm_h03_service_copy_hook),
    .close_hook = ADDRESS(rbm_h03_service_close_hook),
    .boot_and_other_writers_owned = rbm_h03_boot_writers_owned,
};

int rbm_h03_target_ram_owned(void *context)
{
    (void)context;
    return lfj8_h03_ram_owned((void *)&target_owner);
}
