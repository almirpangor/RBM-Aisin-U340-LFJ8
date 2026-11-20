#include "factory_correction.h"
#include "factory_core.h"
#include "factory_phase_modes.h"
#include "donor_calibration.h"
static int32_t s32(uint32_t x) { return x<=0x7fffffffu?(int32_t)x:-1-(int32_t)~x; }
static int16_t s16(uint32_t x) { x&=65535;return (int16_t)(x<32768?(int32_t)x:(int32_t)x-65536); }
static int32_t add(int32_t a,int32_t b) { return s32((uint32_t)a+(uint32_t)b); }
static int32_t sub(int32_t a,int32_t b) { return s32((uint32_t)a-(uint32_t)b); }
static uint16_t word(unsigned offset) { const uint8_t *p=correction_001F5C+offset;return p[0]|((uint16_t)p[1]<<8); }
static int32_t coefficient(unsigned offset) { return s32(word(offset)|((uint32_t)word(offset+2)<<16)); }
int32_t factory_correction_multiply(int32_t a,int32_t b) {
    uint32_t x=a<0?0u-(uint32_t)a:(uint32_t)a,y=b<0?0u-(uint32_t)b:(uint32_t)b;
    uint32_t lo_x=x&65535,lo_y=y&65535,hi_x=x>>16,hi_y=y>>16;
    uint32_t r=((lo_x*lo_y)>>16)+hi_x*lo_y+hi_y*lo_x+
               (((hi_x<<8)&65535)*((hi_y<<8)&65535));
    if((a<0)!=(b<0)) r=0u-r;
    return s32(r);
}
int32_t factory_correction_saturate(int32_t x,uint8_t *flags) {
    if(x>8388607) { if(flags) *flags|=1;return 8388607; }
    if(x< -8388608) { if(flags) *flags|=1;return -8388608; }
    return x;
}
static int valid(const FactoryPressureCorrection *s) { return s && s->index_4514<=5 && s->index_4545<=6; }
static int32_t sat(FactoryPressureCorrection *s,int32_t x) { return factory_correction_saturate(x,&s->flags_p1546); }
static int32_t mul(unsigned c,int32_t x) { return factory_correction_multiply(coefficient(c),x); }
static void correction(FactoryPressureCorrection *s,FactoryCorrectionScratch *w) {
    int32_t memory=s->memory_p1550,state=s->state_p1556,output=s->output_7140;
    int32_t bias=word(0x58+2*(7*s->index_4514+s->index_4545));
    int32_t derivative=sat(s,((int32_t)s->input_7206-s->previous_p1548)*8);
    if(derivative<205) { if(s->count_p1544<255) ++s->count_p1544; }
    else s->count_p1544=0;
    uint32_t f=s->flags_9748;
    if(!(f&1)||(f&0x1c)||!(f&2)||(f&0x220c0u)||!(s->flags_4842&2)||s->input_7184>=23040||
       (s->count_p1544<2 && s->count_4696<18)) {
        s->flags_4830&=(uint8_t)~64;
        goto finish;
    }
    if(!(s->flags_4830&64)) {
        s->flags_4830|=64;s->flags_p1546&=(uint8_t)~1;s->count_p1545=0;
        s->filter_p1568=s->filter_p1564=s->filter_p1560=s->integral_p1552=0;
        memory=output=0;state=-bias;
        for(unsigned i=0;i<5;++i) s->history_p1524[i]=-bias;
    }
    int32_t z[2];
    for(unsigned i=0;i<2;++i) {
        int32_t a=mul(0x10+4*i,output);
        a=factory_div_s32_s16(s32((uint32_t)a<<1),25);
        z[i]=sat(s,add(a,mul(8+4*i,s->filter_p1568)));
    }
    w->slot36=z[0];w->slot40=z[1];
    int32_t difference=sub(z[1],s->filter_p1564);
    uint16_t gain=factory_interp1(s->input_7184,correction_001F5C+0x4c);
    int32_t error=sat(s,sub(s->history_p1524[4],derivative));
    state=sat(s,sub(add(mul(0,state),mul(4,difference)),factory_correction_multiply(gain,error)));
    ++s->count_p1545;
    if(s->count_p1545>=2) {
        for(unsigned i=4;i>0;--i) s->history_p1524[i]=s->history_p1524[i-1];
        s->history_p1524[0]=state;s->count_p1545=0;
    }
    s->integral_p1552=add(s->integral_p1552,state);
    int32_t delta=sat(s,sub(derivative,s->previous_p1572));
    for(unsigned i=0;i<2;++i) z[i]=sat(s,add(mul(0x20+4*i,delta),mul(0x18+4*i,s->filter_p1560)));
    w->slot28=z[0];
    int32_t biased=sat(s,add(bias,state));
    memory=s16((uint32_t)(memory-bias));
    int32_t integrated=sat(s,sub(s->integral_p1552,memory));
    int32_t combined=add(add(mul(0x28,biased),mul(0x2c,integrated)),mul(0x30,z[1]));
    if(combined>32767) { combined=32767;s->flags_p1546|=1; }
    if(combined< -32768) { combined=-32768;s->flags_p1546|=1; }
    output=s16((uint32_t)factory_interp1(s->input_7184,correction_001F5C+0x34)-7680u);
    if(combined>=0) output=s16((uint32_t)factory_interp1(s->input_7184,correction_001F5C+0x40)-7680u);
    if(s->flags_p1546&1) s->flags_4830&=(uint8_t)~64;
finish:
    s->filter_p1568=w->slot36;s->filter_p1564=w->slot40;s->filter_p1560=w->slot28;
    s->state_p1556=state;s->memory_p1550=(int16_t)memory;s->output_7140=(int16_t)output;
    s->previous_p1548=s->input_7206;s->previous_p1572=derivative;
}
int factory_pressure_correction_raw(FactoryPressureCorrection *s,FactoryCorrectionScratch *scratch) {
    if(!valid(s)||!scratch) return 0;
    FactoryPressureCorrection t=*s;FactoryCorrectionScratch w=*scratch;
    correction(&t,&w);*s=t;*scratch=w;return 1;
}
int factory_pressure_correction(FactoryPressureCorrection *s) {
    if(!valid(s)) return 0;
    FactoryCorrectionScratch w={s->filter_p1560,s->filter_p1568,s->filter_p1564};
    return factory_pressure_correction_raw(s,&w);
}
int factory_slt_correction_step(FactoryPressureCorrection *s,const FactorySLTInputs *in,FactorySLTResult *out) {
    if(!valid(s)||!in||!out) return 0;
    FactoryPressureCorrection t=*s;
    if(!factory_pressure_correction(&t)) return 0;
    FactorySLTResult result;
    result.selected_7244=factory_slt_select(in->selected_p1158,t.output_7140,in->limit_7138,
        in->override_7134,(uint8_t)t.flags_9748,t.flags_4830,in->flags_p1156);
    result.characteristic_7132=factory_slt_characteristic((uint16_t)result.selected_7244);
    *s=t;*out=result;return 1;
}
