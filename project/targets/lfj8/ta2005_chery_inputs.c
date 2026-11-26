#include "ta2005_chery_inputs.h"
#include <limits.h>

const uint16_t ta2005_chery_inputs_abi[] = {sizeof(Ta2005CheryInputs), sizeof(Ta2005CherySnapshot)};

static void clear_model(Ta2005CheryModel *model)
{
    model->f9d8 = UINT8_MAX;
    model->f9e8 = UINT8_MAX;
    model->f914 = UINT8_MAX;
}

void ta2005_chery_snapshot_clear(Ta2005CherySnapshot *out)
{
    out->speed_fad8 = UINT16_MAX;
    out->coolant_f9e9 = UINT8_MAX;
    out->usable = 0;
    clear_model(&out->model);
}

void ta2005_chery_inputs_reset(Ta2005CheryInputs *state)
{
    state->speed_received_at = 0;
    state->coolant_received_at = 0;
    state->speed_fad8 = UINT16_MAX;
    state->coolant_f9e9 = UINT8_MAX;
    state->received = 0;
    clear_model(&state->model);
}

unsigned ta2005_chery_inputs_receive(Ta2005CheryInputs *state, uint16_t id,
                                   uint16_t standard_data_dlc, const uint8_t *payload,
                                   const uint32_t *received_at)
{
    if (!state || standard_data_dlc != 8u || !payload || !received_at)
        return 0;

    if (id == 0x0FAu) {
        if ((state->received & TA2005_CHERY_SPEED) &&
            (uint32_t)(*received_at - state->speed_received_at) >= UINT32_C(0x80000000))
            return 0;
        const uint16_t raw = (uint16_t)(((uint16_t)payload[0] << 8) | payload[1]);
        state->speed_fad8 = raw == UINT16_MAX ? UINT16_MAX :
                            raw >= 32767u ? 65534u : (uint16_t)(2u * raw);
        state->speed_received_at = *received_at;
        state->model.f9d8 = payload[2];
        state->model.f9e8 = payload[3];
        state->model.f914 = payload[5];
        state->received |= TA2005_CHERY_SPEED;
        return TA2005_CHERY_SPEED;
    }
    if (id == 0x278u) {
        if ((state->received & TA2005_CHERY_COOLANT) &&
            (uint32_t)(*received_at - state->coolant_received_at) >= UINT32_C(0x80000000))
            return 0;
        unsigned raw = payload[0];
        state->coolant_f9e9 = (uint8_t)(raw == UINT8_MAX ? UINT8_MAX : (3u * raw) / 4u + 2u);
        state->coolant_received_at = *received_at;
        state->received |= TA2005_CHERY_COOLANT;
        return TA2005_CHERY_COOLANT;
    }
    return 0;
}

unsigned ta2005_chery_inputs_snapshot(const Ta2005CheryInputs *state, const uint32_t *now,
                                    uint16_t maximum_age, Ta2005CherySnapshot *out)
{
    if (!out)
        return 0;
    ta2005_chery_snapshot_clear(out);
    if (!state || !now || !maximum_age)
        return 0;
    if ((state->received & TA2005_CHERY_SPEED) &&
        (uint32_t)(*now - state->speed_received_at) < maximum_age) {
        out->model.f9d8 = state->model.f9d8;
        out->model.f9e8 = state->model.f9e8;
        out->model.f914 = state->model.f914;
        if (state->speed_fad8 != UINT16_MAX) {
            out->speed_fad8 = state->speed_fad8;
            out->usable |= TA2005_CHERY_SPEED;
        }
    }
    if ((state->received & TA2005_CHERY_COOLANT) && state->coolant_f9e9 != UINT8_MAX &&
        (uint32_t)(*now - state->coolant_received_at) < maximum_age) {
        out->coolant_f9e9 = state->coolant_f9e9;
        out->usable |= TA2005_CHERY_COOLANT;
    }
    return out->usable;
}
