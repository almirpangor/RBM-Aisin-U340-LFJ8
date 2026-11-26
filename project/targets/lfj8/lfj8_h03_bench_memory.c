#include "lfj8_h03_mmio.h"
#include "lfj8_h03_ram_owner.h"
#include <stddef.h>

#ifndef RBM_H03_BENCH_MEMORY_HEADER
#error "The H03 bench RAM owner needs the header emitted from the pinned H03"
#endif
#ifndef RBM_H03_BENCH_EARLY_LATCHES
#error "The H03 bench RAM owner needs the linked early reset latch stores"
#endif
#include RBM_H03_BENCH_MEMORY_HEADER

static const struct {
    uint32_t address;
    uint32_t word;
} boot_words[] = RBM_H03_BENCH_BOOT_WORDS;

extern const uint8_t rbm_h03_early_irq_bench_latches[];
void rbm_h03_early_irq_gate(void);

int rbm_h03_boot_writers_owned(void *context)
{
    if (context != NULL ||
        (uintptr_t)rbm_h03_early_irq_bench_latches != (uintptr_t)&rbm_h03_early_irq_gate + 0x0cu) {
        return 0;
    }

    /* The RAM owner has already checked ordinary Flash, the linked IRQ and
     * service guards, DMA and stack headroom under the native exclusion. */
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    for (unsigned i = 0; i < sizeof boot_words / sizeof boot_words[0]; ++i) {
        if (io->read32(io->context, boot_words[i].address) != boot_words[i].word) {
            return 0;
        }
    }
    return 1;
}
