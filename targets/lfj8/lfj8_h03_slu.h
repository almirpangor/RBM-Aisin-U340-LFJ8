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

typedef struct {
    uint16_t baseline_7026, override_7082, temperature_7184;
    int16_t offset_7028, offset_7030;
    uint8_t flags_1636, mode_4505;
    uint8_t selector_4544, flags_4834, flags_4828, flags_4827;
    uint8_t flags_4829, flags_4825, flags_4822;
    bool qualified;
} Lfj8H03SluSecondaryInput;

typedef struct {
    uint8_t previous_mode_1637;
    uint8_t timer_4735;
} Lfj8H03SluSecondaryState;

typedef struct {
    uint16_t pressure_7136;
    Lfj8H03SluCommand command;
} Lfj8H03SluSecondaryResult;

/* Execute donor 05DCE8 and the numerical part of 055C5E on one snapshot.
 * The caller supplies the post-05DC5E baseline and serializes the state
 * with the owner that initializes and advances GP-4735. This function
 * resets that timer only on the donor transition and never advances it.
 * Failure preserves state and clears any supplied result. */
bool lfj8_h03_slu_secondary(const Lfj8H03SluSecondaryInput *input,
                           Lfj8H03SluSecondaryState *state, Lfj8H03SluSecondaryResult *result);

typedef struct {
    uint16_t speed_7200, speed_7204, base_7054;
    int16_t trim_7066;
    uint8_t gear;
    uint8_t learning_4616[12];
} Lfj8H03SluBaselineInput;

typedef struct {
    uint16_t baseline_7026;
    int16_t adjustment_7032;
} Lfj8H03SluBaselineState;

/* Run 05DC5E before pressure and command calculation. Qualify both inputs
 * together, including the shared learning bank and the retained owner state.
 * The calculated baseline replaces input->baseline_7026 for this call.
 * Failure preserves both states and clears any supplied result. */
bool lfj8_h03_slu_secondary_from_baseline(const Lfj8H03SluSecondaryInput *input,
                                         const Lfj8H03SluBaselineInput *baseline_input,
                                         Lfj8H03SluBaselineState *baseline_state,
                                         Lfj8H03SluSecondaryState *state,
                                         Lfj8H03SluSecondaryResult *result);

#endif
