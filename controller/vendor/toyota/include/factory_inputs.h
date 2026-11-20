#ifndef RBM_FACTORY_INPUTS_H
#define RBM_FACTORY_INPUTS_H
#include <stdint.h>
/* Raw donor engine variables, NOT pedal percentage or physical torque.
 * Producer scaling on the GW4G15 remains a separate platform contract. */
typedef struct {
    int16_t v9044,v9030,v8310,v8306,v8302,v8298,v8272,v8270;
    uint16_t load7202,load7200,load7198,delta7196;
    uint16_t delta1102,history1104[4];
    uint8_t flags5299,index4861,index4862,count4731,count1100,flags1101;
} FactoryLoadInputs;
uint16_t factory_load_primary(const FactoryLoadInputs *s); /* 054C00 */
uint16_t factory_load_limited(const FactoryLoadInputs *s); /* 054BD4 */
uint16_t factory_load_difference(const FactoryLoadInputs *s); /* 054CCA */
void factory_load_main(FactoryLoadInputs *s); /* 054AB2 */
void factory_load_observer(FactoryLoadInputs *s); /* 054B34 */
/* 054260..0542F6, calling 012E2E; counters are GP -4816..-4620.
 * Serialized single owner, no concurrent ISR modification permitted.
 * This does NOT advance phase: the original increments GP+1060 only after
 * all fast-task functions. No period in milliseconds is asserted here. */
void factory_counter_banks(uint8_t counters[197],uint8_t phase);
#endif
