#ifndef RBM_FACTORY_LEARNING_H
#define RBM_FACTORY_LEARNING_H
#include "factory_learning_state.h"
/* Numerical donor units. Caller owns scheduler, coherent inputs and shared GP
 * exchange. All functions reject invalid table access without committing state. */
int factory_engagement_fill(FactoryLearning *s);    /* 05A378 */
int factory_engagement_edge(FactoryLearning *s);    /* 05A5B8 */
int factory_engagement_override(FactoryLearning *s);/* 05A61E */
int factory_engagement_step(FactoryLearning *s);    /* 5A5B8 -> 5A378 -> 5A61E */
int factory_learning_up(FactoryLearning *s);        /* 05A63A */
int factory_learning_up_observer(FactoryLearning *s);/* 05A988 */
int factory_learning_down(FactoryLearning *s);      /* 05AA5C */
int factory_learning_down_observer(FactoryLearning *s);/* 05AD5E */
/* 012F9C receives a full 32-bit register. New call sites double a uint16_t
 * without ZXH: they must not truncate values above 65535. */
uint16_t factory_learning_interp(uint32_t q,const uint8_t *table);
#endif
