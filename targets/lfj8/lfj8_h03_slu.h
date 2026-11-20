#ifndef RBM_LFJ8_H03_SLU_H
#define RBM_LFJ8_H03_SLU_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t pressure_7136;
    uint8_t selector_4544;
    uint8_t flags_4834;
    uint8_t flags_4828;
    uint8_t flags_4827;
    uint8_t flags_4829;
    uint8_t flags_4825;
    uint8_t flags_4822;
    bool qualified;
} Lfj8H03SluInput;

typedef struct {
    uint16_t selected_7246;
    uint16_t characteristic_7130;
    bool force;
} Lfj8H03SluCommand;

/* Use a coherent, qualified SECONDARY snapshot after the donor 05DCE8
 * pressure calculation. Reproduce 055C5E's numerical selection and its
 * choice of normal/forced branch. On failure, clear any previous command.
 * A valid result is in donor units and conveys no authority over H03 I/O. */
bool lfj8_h03_slu_command(const Lfj8H03SluInput *input, Lfj8H03SluCommand *command);

#endif
