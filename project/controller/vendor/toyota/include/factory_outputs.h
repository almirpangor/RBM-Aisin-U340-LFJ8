#ifndef RBM_FACTORY_OUTPUTS_H
#define RBM_FACTORY_OUTPUTS_H
#include <stdint.h>
/* Donor driver commands, not GPIO levels. Modes 3..6 require the donor
 * driver state machine; they must NOT be treated as boolean ON/OFF. */
typedef struct { uint8_t mode, channel; } FactoryDriverCommand;
typedef struct { uint8_t count; FactoryDriverCommand commands[4]; } FactoryDriverBatch;
typedef struct {
    uint8_t index_4852, index_4850, previous_p1369, flags_4838;
    uint8_t flags_7189, flags_7187, flags_4845, index_4847;
    uint8_t value_4533, speed_4548, flags_4844, value_4547;
    uint8_t flags_p1368, value_4528, gates_4532[4], index_4848;
    uint8_t event_p2121, event_p2129;
} FactoryShiftOutputState;
/* 0574C4..057690, including event helpers 0626F2/06CD9C/06D148.
 * Status inputs are the signed returns of donor 026174 for channels 0/1.
 * Returns 0 without modifications for a selected index outside 0..3.
 * Batch is overwritten on success, retains donor call order. */
int factory_shift_outputs(FactoryShiftOutputState *s, int8_t status0,
    int8_t status1, FactoryDriverBatch *batch);
typedef struct {
    uint8_t flags_4832, flags_4831, flags_4835, flags_7125;
    uint8_t count_4753, previous_p1424, count_4804, flags_4833, event_p2157;
} FactorySTOutputState;
/* 058C7C..058D40, including event helper 062708/06E25A.
 * Counter increment/scheduler are external, not assumed milliseconds. */
int factory_st_output(FactorySTOutputState *s, int8_t status5,
    FactoryDriverBatch *batch);
typedef struct {
    uint8_t requested_5314, inhibit_5311, override_5308, forced_5305, state_5302;
} FactoryDriverState;
typedef struct { uint8_t write_pending, channel, value; } FactoryDriverWrite;
/* 025FFC dispatcher + 026188..026352 helpers, at boundary 01DD02.
 * Valid donor channels 0/1/5, commands 0..10, states 0..4.
 * Interrupt exclusion belongs to the caller; no target MMIO is performed. */
int factory_driver_dispatch(FactoryDriverState *s, uint8_t mode,
    uint8_t channel, FactoryDriverWrite *write);
#endif
