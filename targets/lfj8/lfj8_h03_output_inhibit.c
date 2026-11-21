#include "lfj8_h03_output_inhibit.h"

#include <stdint.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

void lfj8_h03_output_inhibit_locked(void *context)
{
    (void)context;

    /* Match the zero-command branches of 00CA78, 00CADC and 00CB40. */
    REG8(0x800703) &= 0x7fu;
    REG8(0x800703) &= 0xbfu;
    REG8(0x800703) &= 0xdfu;

    /* Match 00B58C with zero requested width. Set the low latch before
     * selecting GPIO to preserve the OEM switch sequence. */
    REG16(0x8048cc) = 0;
    REG8(0x80070a) &= 0xfeu;
    REG8(0x80074a) &= 0xfeu;
    REG16(0x8048cc) = 1;
    REG16(0x800344) = 2998;
    REG16(0x800346) = 0;

    /* Match the zero-width branch of 00B4B4. Keep the GPIO latch low
     * before switching P97 away from TIO9, as in the OEM sequence. */
    REG16(0x8048ce) = 0;
    REG8(0x800709) &= 0xfeu;
    REG8(0x800749) &= 0xfeu;
    REG16(0x8048ce) = 1;
    REG16(0x800394) = 248;
    REG16(0x800396) = 0;
    /* OEM apply rebuilds the width from this proposal. */
    REG32(0x8060f0) = 0;

    /* Retire both owned command banks. A subsequent OEM arbitration with
     * unchanged qualifiers must not recover the withdrawn proposal. */
    REG8(0x8063d5) = 0;
    REG8(0x8063d7) = 0;
    REG8(0x8063d8) = 0;
    REG8(0x8063da) = 0;
    REG8(0x8063db) = 0;
    REG8(0x8063dd) = 0;
    REG32(0x80508c) = 0;
    REG32(0x805094) = 0;
}
