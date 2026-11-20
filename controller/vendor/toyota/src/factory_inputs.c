#include "factory_inputs.h"
#include "factory_core.h"
#include "donor_calibration.h"
/* Explicit halfword wrap avoids implementation-defined signed narrowing. */
static int32_t sh(uint32_t v) { v&=65535u;return v&32768u?(int32_t)v-65536:(int32_t)v; }
static int32_t abs16(int32_t v) { return v<0?sh((uint32_t)-v):v; }
uint16_t factory_load_primary(const FactoryLoadInputs *s) {
    int32_t v=786;
    if(!(s->flags5299&2)) {
        v=s->v8270;if(v<s->v8306) v=s->v8306;if(v<0) v=0;
    }
    return factory_load_code((uint16_t)v);
}
uint16_t factory_load_limited(const FactoryLoadInputs *s) {
    int32_t v=786;
    if(!(s->flags5299&2)) {
        v=s->v8272;
        if(v<s->v8306) v=s->v8306;if(v<s->v8298) v=s->v8298;
        if(v>s->v8302) v=s->v8302;if(v>s->v8310) v=s->v8310;
        if(v<0) v=0;
    }
    return factory_load_code((uint16_t)v);
}
uint16_t factory_load_difference(const FactoryLoadInputs *s) {
    int32_t v=786;
    if(!(s->flags5299&2)) { v=sh((uint32_t)((int32_t)s->v9044-s->v9030));if(v<0) v=0; }
    return factory_load_code((uint16_t)v);
}
void factory_load_main(FactoryLoadInputs *s) {
    s->load7202=(uint16_t)((factory_load_primary(s)+64u)&65408u);
    s->load7200=(uint16_t)((factory_load_limited(s)+64u)&65408u);
    s->load7198=(uint16_t)((factory_load_difference(s)+64u)&65408u);
    s->delta7196=s->delta1102;
    unsigned q=s->load7202>>7,i=0;
    /* q<=200, immutable final threshold=255; bounded for defensive indexing. */
    while(i+1<sizeof input_load_000D14 && q>=input_load_000D14[i]) ++i;
    if(i<s->index4861 && q>=(uint8_t)(input_load_000D14[i]-5u)) ++i;
    s->index4861=(uint8_t)i;s->index4862=(uint8_t)(i>=10?i-5:i>>1);
}
void factory_load_observer(FactoryLoadInputs *s) {
    s->count1100=(uint8_t)(s->count1100+1u);if(s->count1100<4) return;
    uint16_t raw=factory_load_primary(s);unsigned jump=0;
    if(abs16(sh((uint32_t)raw-s->history1104[0]))>=15360) { s->count4731=0;jump=1; }
    int32_t delta=sh((uint32_t)raw-s->history1104[3]);
    if(abs16(delta)<2560) { if(s->count4731>=6) s->flags1101&=(uint8_t)~1u; }
    else if(jump) s->flags1101|=1;
    s->delta1102=(s->flags1101&1)?0:(uint16_t)delta;
    for(unsigned i=3;i;i--) s->history1104[i]=s->history1104[i-1];
    s->history1104[0]=raw;s->count1100=0;
}
void factory_counter_banks(uint8_t counters[197],uint8_t phase) {
    static const uint8_t end[8]={32,82,154,181,189,195,196,197};
    unsigned begin=0;
    for(unsigned bank=0;bank<8;++bank) {
        unsigned mask=(1u<<bank)-1u;
        if(!bank || (phase&mask)==(mask>>1))
            for(unsigned i=begin;i<end[bank];++i) if(counters[i]!=255) ++counters[i];
        begin=end[bank];
    }
}
