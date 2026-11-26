#ifndef RBM_GEAR_INTERNAL_H
#define RBM_GEAR_INTERNAL_H
#include "factory_gears.h"
#include "factory_core.h"
#include "factory_phase_modes.h"
#include "donor_calibration.h"
#define B(n) (s->b##n)
#define P(n) (s->p##n)
#define U(n) (s->u##n)
#define V(n) (s->v##n)
#define H(n) sx16(U(n))
#define J(n) sx16(V(n))
#define SET(v,m) ((v)|=(m))
#define CLR(v,m) ((v)&=(uint8_t)~(m))
static inline int32_t sx16(uint32_t x) { x&=65535u; return x<32768u?(int32_t)x:(int32_t)x-65536; }
static inline int32_t sx8(uint32_t x) { x&=255u; return x<128u?(int32_t)x:(int32_t)x-256; }
static inline int32_t sx32(uint32_t x) { return x<=0x7fffffffu?(int32_t)x:-1-(int32_t)~x; }
static inline int32_t sar(int32_t x,unsigned n) { return x>=0?x/(1<<n):-1-((-1-x)/(1<<n)); }
static inline int32_t cap(int32_t x,int32_t lo,int32_t hi) { return x<lo?lo:x>hi?hi:x; }
static inline const uint8_t *rom(uint32_t a) {
    /* Only verified constant addresses and the 12 verified pointers in B1E0. */
    return a<0x1108u?gear_000D08+(a-0xd08u):a<0xb198u?gear_001108+(a-0x1108u):gear_00B198+(a-0xb198u);
}
static inline uint16_t ru16(uint32_t a) { const uint8_t *p=rom(a);return p[0]|((uint16_t)p[1]<<8); }
static inline uint32_t ru32(uint32_t a) { return ru16(a)|((uint32_t)ru16(a+2)<<16); }
static inline uint8_t rb(uint32_t a) { return *rom(a); }
static inline uint16_t interp(uint16_t x,uint32_t a) { return factory_interp1(x,rom(a)); }
static inline int valid_gear(const FactoryGearState *s) {
    return s && B(4854)<=3 && B(4853)<=3 && B(4852)<=3 && B(4851)<=3 && B(4862)<=7 && P(1165)<=3;
}
void gear_565ce(FactoryGearState *s);
void gear_56eda(FactoryGearState *s);
void gear_571e2(FactoryGearState *s);
void gear_57210(FactoryGearState *s);
void gear_5715e(FactoryGearState *s);
void gear_571b4(FactoryGearState *s);
void gear_5722e(FactoryGearState *s);
void gear_57074(FactoryGearState *s);
void gear_5724c(FactoryGearState *s,unsigned channel);
uint8_t gear_567b6(FactoryGearState *s);
uint8_t gear_56b88(FactoryGearState *s);
uint8_t gear_5737e(FactoryGearState *s);
#endif
