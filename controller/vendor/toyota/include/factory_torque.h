#ifndef RBM_FACTORY_TORQUE_H
#define RBM_FACTORY_TORQUE_H
#include "factory_torque_state.h"
/* Valid raw donor state, no physical-unit or CAN-percentage conversion.
 * Functions are atomic on invalid table indices and return 1 on success. */
int factory_torque_lookup(const FactoryTorque *s,unsigned slot,unsigned parameter,unsigned gear,uint8_t *value);
int factory_torque_58162(FactoryTorque *s);
int factory_torque_58276(FactoryTorque *s);
int factory_torque_5841e(FactoryTorque *s);
int factory_torque_5849a(FactoryTorque *s,unsigned slot);
int factory_torque_58522(FactoryTorque *s);
int factory_torque_585f0(FactoryTorque *s);
int factory_torque_5883e(FactoryTorque *s);
int factory_torque_589a2(FactoryTorque *s);
int factory_torque_58a92(FactoryTorque *s);
int factory_torque_58bb0(FactoryTorque *s);
int factory_torque_58c30(FactoryTorque *s);
/* Exact donor main sequence 054178..05418C (exclusive), including 058C76. */
int factory_torque_step(FactoryTorque *s);
/* Donor-engine reference model, 030EB8. This is NOT the GW4G15 actuator.
 * Used to validate the nature and acceptance of the OEM signed request. */
typedef struct {
    uint16_t request8380,previous8378,input8946,input9418;
    uint8_t flags5140,flags5139,accepted5138;
} FactoryDonorEngineGate;
void factory_donor_engine_gate(FactoryDonorEngineGate *s);
#endif
