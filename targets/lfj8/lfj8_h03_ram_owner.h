#ifndef RBM_LFJ8_H03_RAM_OWNER_H
#define RBM_LFJ8_H03_RAM_OWNER_H

#include "lfj8_h03_service_guard.h"

typedef struct {
    Lfj8H03ServiceRange control, communication, workspace, dtc_irq_pointer;
    Lfj8H03ServiceRange spi, psw;
    uint32_t spi_reserve_bytes, psw_reserve_bytes;
    uint32_t direct_hook, span_hook, copy_hook, close_hook;
    void *platform;
    int (*boot_and_other_writers_owned)(void *platform);
} Lfj8H03RamOwner;

/* Lfj8H03ApplicationBinding.ram_owned adapter. The platform passes a
 * read-only linker-bound context and holds the native interrupt exclusion.
 * The boot witness must already have a safe stack and verify that other
 * writers and the initial IRQ ordering are covered. The native DMA check
 * reads live destinations and counts only. The boot witness must guarantee
 * that subsequent DMA reconfiguration is contained and that other writers,
 * including SBI, remain covered. It must not inspect project RAM to decide
 * whether RAM can be accessed.
 * Supply the required remaining SPI/PSW reserves in bytes for the final
 * image. The native check reads CR2 and the OEM PSW cursor under the lock.
 * It assumes the existing entry frame was already placed safely.
 * The caller must close the lifecycle gate before allowing a service owner
 * or a different memory map. CAN may be parked while this probe runs. */
int lfj8_h03_ram_owned(void *context);

/* Required platform witness for rbm_h03_target_ram_owned. It is called under
 * native interrupt exclusion with a null context, before project RAM may
 * safely be read or written. Return 1 only when the startup order, remaining
 * CPU/SBI writers and DMA reconfiguration paths are qualified for this image.
 * The release link has no fallback definition. */
int rbm_h03_boot_writers_owned(void *context);

#endif
