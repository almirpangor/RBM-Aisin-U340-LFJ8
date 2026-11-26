#include "factory_outputs.h"

int factory_driver_dispatch(FactoryDriverState *s, uint8_t mode,
    uint8_t channel, FactoryDriverWrite *w)
{
    static const uint8_t actions[55] = {
        0,255,255,255,255, 255,1,7,7,7, 255,2,8,8,8,
        255,3,3,255,13, 255,255,255,4,14, 255,255,255,11,15,
        255,255,255,12,16, 255,5,255,9,9, 255,255,6,10,10,
        255,17,17,17,17, 255,255,255,255,18
    };
    if (!s || !w || mode > 10 || s->state_5302 > 4 ||
        (channel != 0 && channel != 1 && channel != 5)) return 0;
    w->write_pending = 0; w->channel = channel; w->value = 0;
    int next = -1, output = -1;
    switch (actions[mode * 5 + s->state_5302]) {
    case 0: next = 1; break;
    case 1: output = 1; s->requested_5314 = 1; break;
    case 2: output = 0; s->requested_5314 = 0; break;
    case 3: s->override_5308 = 1; next = 3; break;
    case 4:
        s->override_5308 = s->forced_5305 = 0;
        if (s->inhibit_5311 == 0) { output = s->requested_5314; next = 1; }
        else { output = 0; next = 2; }
        break;
    case 5: output = 0; s->inhibit_5311 = 1; next = 2; break;
    case 6: output = s->requested_5314; s->inhibit_5311 = 0; next = 1; break;
    case 7: s->requested_5314 = 1; break;
    case 8: s->requested_5314 = 0; break;
    case 9: s->inhibit_5311 = 1; break;
    case 10: s->inhibit_5311 = 0; break;
    case 11: output = 1; s->forced_5305 = 1; break;
    case 12: output = 0; s->forced_5305 = 0; break;
    case 13: s->override_5308 = 1; break;
    case 14: s->override_5308 = s->forced_5305 = 0; break;
    case 15: s->forced_5305 = 1; break;
    case 16: s->forced_5305 = 0; break;
    case 17: output = 0; next = 4; break;
    case 18:
        if (s->override_5308 == 1) { output = s->forced_5305; next = 3; }
        else if (s->inhibit_5311 == 1) { output = 0; next = 2; }
        else { output = s->requested_5314; next = 1; }
        break;
    default: break;
    }
    if (next >= 0) s->state_5302 = (uint8_t)next;
    if (output >= 0) { w->write_pending = 1; w->value = (uint8_t)output; }
    return 1;
}

static void emit(FactoryDriverBatch *b, uint8_t mode, uint8_t channel)
{
    b->commands[b->count].mode = mode;
    b->commands[b->count++].channel = channel;
}

int factory_shift_outputs(FactoryShiftOutputState *s, int8_t status0,
    int8_t status1, FactoryDriverBatch *b)
{
    /* Exact 32 bytes at donor ROM B1B4; four gear indices per fault bank. */
    static const uint8_t table[32] = {
        0,1,2,3, 3,2,2,3, 1,1,2,2, 2,2,2,2,
        0,1,2,3, 2,2,2,3, 1,1,2,2, 2,2,2,2
    };
    if (!s || !b) return 0;
    uint8_t index = (s->flags_4838 & 16) ? s->index_4850 : s->index_4852;
    if (index > 3) return 0;
    if (index != s->previous_p1369) {
        s->flags_4838 |= 2;
        s->event_p2121 = s->event_p2129 = 1;
    } else s->flags_4838 &= (uint8_t)~2;
    s->previous_p1369 = index;
    uint8_t fault_bank = 0, variant = 0;
    if (!(s->flags_4838 & 2)) {
        if (status0 == 2) {
            variant = !!(s->flags_7189 & 16);
            fault_bank = 1;
        }
        if (status1 == 2) {
            if (s->flags_7187 & 16) variant = 1;
            fault_bank += 2;
        }
    }
    if (s->flags_4845 & 4) variant = 0;
    uint8_t output = table[index + 4 * (fault_bank + 4 * variant)];
    s->value_4528 = 1;
    s->flags_p1368 &= (uint8_t)~1;
    uint8_t candidate = s->value_4533;
    if (candidate) --candidate;
    if (s->speed_4548 < 50) {
        s->gates_4532[0] = s->gates_4532[1] = 0;
        s->gates_4532[2] = s->index_4847 == 3 && !(s->flags_4844 & 8);
        s->gates_4532[3] = s->index_4847 < 2 || !(s->flags_4844 & 8);
    } else {
        for (uint8_t i = 0; i < 4; ++i) s->gates_4532[i] = 1;
    }
    if (s->value_4547 == 90 && candidate < 4 && !s->gates_4532[candidate]) {
        s->flags_p1368 |= 1;
        output = candidate;
    }
    s->index_4848 = output;
    s->flags_4838 &= (uint8_t)~12;
    if (output <= 1) s->flags_4838 |= 4;
    if (output == 0 || output == 3) s->flags_4838 |= 8;
    b->count = 0;
    if (s->flags_p1368 & 1) {
        if (!(s->flags_p1368 & 2)) {
            emit(b, 3, 0); emit(b, 3, 1);
            s->flags_p1368 |= 2;
        }
        emit(b, (s->flags_4838 & 4) ? 5 : 6, 0);
        emit(b, (s->flags_4838 & 8) ? 5 : 6, 1);
    } else {
        if (s->flags_p1368 & 2) {
            emit(b, 4, 0); emit(b, 4, 1);
            s->flags_p1368 &= (uint8_t)~2;
        }
        emit(b, (s->flags_4838 & 4) ? 1 : 2, 0);
        emit(b, (s->flags_4838 & 8) ? 1 : 2, 1);
    }
    return 1;
}

int factory_st_output(FactorySTOutputState *s, int8_t status5,
    FactoryDriverBatch *b)
{
    if (!s || !b) return 0;
    uint8_t on = 0;
    if (s->flags_4832 & 32) on = (s->flags_4832 >> 6) & 1;
    if (s->flags_4831 & 1) on = (s->flags_4831 >> 1) & 1;
    if (s->flags_4832 & 2) on = (s->flags_4832 >> 2) & 1;
    if (s->flags_4832 & 8) on = (s->flags_4832 >> 4) & 1;
    uint8_t bit5 = (s->flags_4835 >> 5) & 1;
    if (!bit5) s->count_4753 = 0;
    if ((s->flags_7125 & 16) && bit5 && s->count_4753 < 8) on = 1;
    if (on != (s->previous_p1424 & 1)) {
        s->flags_4832 |= 1;
        s->count_4804 = 0;
        s->event_p2157 = 1;
    }
    s->previous_p1424 = (s->previous_p1424 & (uint8_t)~1) | on;
    if (s->count_4804 >= 8) s->flags_4832 &= (uint8_t)~1;
    if (status5 == 2 && !(s->flags_4832 & 1)) on = 0;
    s->flags_4833 = (s->flags_4833 & 127) | (on << 7);
    b->count = 0;
    emit(b, on ? 1 : 2, 5);
    return 1;
}
