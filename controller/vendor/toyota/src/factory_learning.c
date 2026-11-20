#include "factory_learning.h"
#include "factory_core.h"
#include "factory_phase_modes.h"
#include "donor_calibration.h"
static int16_t sh(uint32_t x) { x&=65535;return (int16_t)(x<32768?(int32_t)x:(int32_t)x-65536); }
static int8_t sb(uint32_t x) { x&=255;return (int8_t)(x<128?(int)x:(int)x-256); }
static int32_t sw(uint32_t x) { return x<=0x7fffffffu?(int32_t)x:-1-(int32_t)~x; }
static int32_t add(int32_t a,int32_t b) { return sw((uint32_t)a+(uint32_t)b); }
static int32_t sub(int32_t a,int32_t b) { return sw((uint32_t)a-(uint32_t)b); }
static int32_t sar(int32_t x,unsigned n) { return x>=0?x/(int32_t)(1u<<n):-1-(int32_t)((~(uint32_t)x)>>n); }
static uint8_t byte(unsigned a) { return learning_001C3C[a-0x1c3c]; }
static uint16_t word(unsigned a) { return byte(a)|((uint16_t)byte(a+1)<<8); }
static int16_t half(unsigned a) { return sh(word(a)); }
static int32_t clamp(int32_t v,int32_t lo,int32_t hi) { return v<lo?lo:v>hi?hi:v; }
static void inc(uint8_t *p) { if(*p<255) ++*p; }
uint16_t factory_learning_interp(uint32_t q,const uint8_t *t) {
    if(q>65535) return (uint16_t)(t[2*t[0]]<<8);
    return factory_interp1((uint16_t)q,t);
}
static uint16_t interp(uint32_t q,unsigned a) { return factory_learning_interp(q,learning_001C3C+a-0x1c3c); }
static int fill(FactoryLearning *s) {
    int32_t peak=s->v1476,peak2=s->v1474;
    peak=sh((uint32_t)peak);peak2=sh((uint32_t)peak2);
    s->b4830=(s->b4830&~4u)|((s->b4830&2u)<<1);
    if(s->b4548>=10||(s->b4823&32)||(s->b4845&8)) { s->b4830&=~1u;goto done; }
    if(s->b4844&1) {
        s->b4690=s->b4801=s->p1472=0;peak=peak2=0;
        s->b4830=(s->b4830|1u)&~6u;s->p1473&=~31u;
        if(s->u7164>=25600) s->p1473|=1;
    }
    if(!(s->b4830&1)) goto done;
    if(s->b4848>3) return 0;
    s->b4841|=4;
    if(s->u7200>word(0x1c54)||(s->b8198&1)) s->p1473|=8;
    unsigned a=s->p1473&1,b=!!(s->b7252&8),c=!!(s->p1473&8);
    int32_t input=sh(s->u7186),speed=sh(s->u7204);
    if(peak<input) peak=sar(input,5)*32;
    if(peak2<speed) peak2=sar(speed,5)*32;
    if(!(s->b4846&16)&&s->b4690<153&&input-peak2<320) s->p1473|=4;
    if((s->p1473&4)&&peak2-speed>=192) s->p1473|=2;
    uint32_t q=(uint32_t)peak<<2;if(q>65280) q=65280;
    uint16_t load=(uint16_t)(s->u7200*2u);
    int32_t pressure=interp(q,0x1c58+9*(b+2*a));
    if((s->p1473&8)&&s->b4801>=byte(0x1c56)) {
        if(s->p1473&16) pressure=s->v1478*2;
        s->p1473|=16;pressure-=interp(load,0x1ca4+11*b);
        int32_t low=interp(load,0x1c7c+19*b);if(pressure<low) pressure=low;
    }
    unsigned row=c+2*b;
    s->u7134=s->v1478=(uint16_t)(((uint32_t)pressure&65534u)>>1);
    int32_t error=sub(speed,s->d9732[s->b4848]);
    if(s->b7252&8) error=speed-sar(sh(learning_000D00[16]|((uint16_t)learning_000D00[17]<<8))*sh(s->u7208),12);
    inc(&s->p1472);
    if(error>=half(0x1c3c+2*row)||error<half(0x1c44+2*row)) s->p1472=0;
    if((s->p1473&2)&&s->p1472>=5) s->b4830|=2;
    else s->b4802=0;
    if(((s->b4830&2)&&s->b4802>=byte(0x1c4c+row))||s->b4690>=byte(0x1c50+row)) s->b4830&=~1u;
done:
    s->v1476=(uint16_t)peak;s->v1474=(uint16_t)peak2;return 1;
}
static int edge(FactoryLearning *s) {
    if(s->b7252&8) s->b4800=0;
    if(s->b7252&1) {
        if(!(s->b7250&1)) {
            s->b4656=209;s->p1480=(s->p1480|1u)&~2u;
            if(s->b4800<49) s->p1480|=2;
        }
    } else s->p1480&=~1u;
    if(s->b4656==255) s->p1480&=~3u;
    /* Donor TST1 bit 1 has no conditional branch: output follows bit 0. */
    if(s->p1480&1) { s->b4841|=4;s->u7134=25600; }
    return 1;
}
static int override(FactoryLearning *s) {
    s->p1484&=~1u;
    if(s->b4823&32) { s->p1484|=1;s->b4841|=4;s->u7134=25600; }
    return 1;
}
static int engagement(FactoryLearning *s) { return edge(s)&&fill(s)&&override(s); }
static void cancel_up(FactoryLearning *s) { s->p1488&=~3u;s->b4830&=~48u; }
static int up(FactoryLearning *s) {
    unsigned mode=(s->flags9748>>2)&7;
    if(s->b4854>s->b4853&&((s->b4845&128)||((s->b4845&64)&&s->b4853))) s->p1488|=4;
    s->b4830&=~8u;
    if((s->flags9748&2)&&!(s->b4843&128)&&s->u7184>=23040&&s->u7184<38400&&
       (s->b4842&2)&&!(s->b4834&64)) {
        if(mode>2) return 0;
        uint32_t q=(uint32_t)s->u7202*2;
        if(s->u7094>=(interp(q,0x1d70+26*mode)>>1)&&s->u7094<(interp(q,0x1d7d+26*mode)>>1)) s->b4830|=8;
    }
    if(!(s->b4830&16)) {
        if(!(s->b4830&8)) cancel_up(s);
        else if(s->b4838&2) {
            if(mode>2) return 0;
            if((int)s->b4847!=(int)s->b4848-1||s->count4511[mode]<byte(0x1cdc+mode)||
               (s->p1488&4)||(mode==2&&s->u7224)||(s->b9736&1)) cancel_up(s);
            else { s->b4655=0;s->p1488|=1;s->v1492=(uint16_t)mode;s->b4515=s->b4514;s->b4516=s->b4545; }
        }
    }
    if((s->b4840&4)||!(s->b4841&16)) s->p1488&=~4u;
    if(!(s->p1488&1)) return 1;
    unsigned row=s->b4515,col=s->b4516;
    if(mode>2||row>5||col>6) return 0;
    unsigned limit=byte(0x1dc0+(6*mode+row)*7+col)+(interp(s->u7184,0x1d40+15*mode)>>8);
    if(limit>255) limit=255;
    if(!(s->b4843&4)&&s->b4655>=limit&&!(s->b4830&16)) s->b4830|=48;
    if((s->flags9748&1)&&(!(s->b9736&1)||!(s->b4838&2))) return 1;
    mode=s->v1492;if(mode>2) return 0;
    unsigned split=byte(0x1e40+mode),group=row>=split,mask=learning_000D00[mode];
    unsigned unlearned=!(s->learned4619[group]&mask);
    if(!(s->b4830&16)||(s->b4842&1)) { cancel_up(s);return 1; }
    int32_t delta=sh((uint32_t)sh(s->u7102)-byte(0x1e44+(6*mode+row)*7+col));
    unsigned idx=2*mode+unlearned;
    uint32_t gain=((uint32_t)word(0x1d00+2*idx)*byte(0x1ce2+mode))>>6;
    if(gain>32767) gain=32767;
    int32_t correction=0;
    if(!(s->p1488&2)&&delta>half(0x1cc4+2*mode)) {
        correction=sh((uint32_t)sar((int32_t)gain*delta,12));
        int32_t max=half(0x1ce8+2*(unlearned+2*(group+2*mode)));
        if(correction>max) correction=max;
    }
    if(delta<half(0x1ccc+2*mode)) correction=-(int32_t)byte(0x1cd4+idx);
    if(s->b4830&32) correction=sh((uint32_t)-half(0x1d0c+2*idx));
    unsigned start=row,end=row+1;
    if(unlearned) { start=group?split:0;end=group?6:split; }
    int32_t learned=sh((uint32_t)(correction+s->learned4579[6*mode+row]));
    for(unsigned r=start;r<end;++r) s->learned4579[6*mode+r]=(int8_t)clamp(learned,sb(byte(0x1d2c+6*mode+r)),sb(byte(0x1d18+6*mode+r)));
    unsigned ci=group+2*mode;inc(&s->count4600[ci]);
    if(!(s->learned4619[group]&mask)&&s->count4600[ci]>=byte(0x1cbc+ci)) s->learned4619[group]+=(uint8_t)mask;
    cancel_up(s);return 1;
}
static int up_observer(FactoryLearning *s) {
    if(!(s->p1488&1)||(s->b4830&16)) return 1;
    unsigned mode=(s->flags9748>>2)&7;if(mode>2) return 0;
    int16_t input=sh(s->u7206);
    if(!(s->b4843&4)) { s->b4799=0;s->v1490=(uint16_t)input; }
    int32_t a=s->d9732[4+mode],b=s->d9732[5+mode];
    int16_t q=factory_div_s32_s16(sh((uint32_t)sub(a,input))*25600,sh((uint32_t)sub(a,b)));
    if(sb((uint32_t)sar(q,8))>sb(byte(0x1cdf+mode))) {
        s->b4830|=16;
        int32_t d=sh((uint32_t)(sh(s->v1490)-input));
        int32_t v=sar(d*factory_div_s32_s16(9375,s->b4799),12);
        if(v>1023) v=1023;s->u7102=(uint16_t)v;
    }
    if(s->flags9748&0x40000u) s->p1488|=2;
    return 1;
}
static void cancel_down(FactoryLearning *s) { s->p1500&=~51u; }
static int down(FactoryLearning *s) {
    int32_t integral=sh(s->v1504),derivative=sh(s->v1506);
    if(s->b4847==3&&s->b4848==2) {
        s->v1514=s->u7200;s->p1500&=~128u;
        if(sh(s->u7196)>=half(0x1ee0)) s->p1500|=128;
    }
    if((s->p1500&48)!=48) {
        uint32_t q=(uint32_t)s->u7202*2;
        int qualified=!(s->b4843&128)&&s->u7184>=23040&&s->u7184<38400&&s->u7154>=7680&&
            s->u7200+1280>=s->v1514&&(s->b4842&8)&&
            s->u7094>=(interp(q,0x1f0c)>>1)&&s->u7094<(interp(q,0x1f19)>>1);
        if(!qualified) cancel_down(s);
        else if(s->b4838&2) {
            if(s->b4847!=3||s->b4848!=2||(s->b9736&1)) cancel_down(s);
            else { s->p1500=(s->p1500|1u)&~68u;s->p1499=s->b4519; }
        }
    }
    if((s->p1500&1)&&(s->b9644&7)>=3) s->p1500|=64;
    if(!(s->p1500&1)||(s->flags9748&1)) return 1;
    unsigned row=s->p1499;if(row>4) return 0;
    unsigned split=byte(0x1ee6),group=row>=split,mask=learning_000D00[3];
    unsigned unlearned=!(s->learned4619[group]&mask);
    if((s->p1500&48)==48&&!(s->p1500&128)&&!(s->b4842&1)) {
        int32_t correction=0;
        if(derivative>half(0x1ef8+2*(row+5*unlearned))&&s->p1496<byte(0x1ee8+row)) {
            correction=sh((uint32_t)sar(derivative*half(0x1ecc+2*unlearned),14));
            if(correction>=half(0x1ed8+2*unlearned)) correction=half(0x1ed8+2*unlearned);
        } else if(integral<half(0x1f28+2*row)&&s->p1496>=byte(0x1ef0+row)) correction=half(0x1edc+2*unlearned);
        else if(integral>half(0x1f34+2*row)) {
            correction=sh((uint32_t)sar(sh((uint32_t)(integral-half(0x1f34+2*row)))*half(0x1ed0+2*unlearned),14));
            if(correction>=half(0x1ed8+2*unlearned)) correction=half(0x1ed8+2*unlearned);
            if(s->p1500&64) correction+=half(0x1ed4+2*unlearned);
            correction=-correction;
            if(!(s->b4603&learning_00B240[group])) s->b4603+=learning_00B240[group];
        }
        int32_t learned=clamp(sh((uint32_t)(correction+s->learned4554[row])),-40,40);
        if(unlearned) {
            unsigned start=group?split:0,end=group?5:split;
            for(unsigned r=start;r<end;++r) s->learned4554[r]=(int8_t)learned;
            inc(&s->count4594[group]);
        } else s->learned4554[row]=(int8_t)learned;
    }
    if(!(s->learned4619[group]&mask)&&
       (((s->b4603&learning_00B240[group])&&s->count4594[group]>=byte(0x1ee2+group))||
         s->count4594[group]>=byte(0x1ee4+group))) s->learned4619[group]+=(uint8_t)mask;
    cancel_down(s);return 1;
}
static int down_observer(FactoryLearning *s) {
    if(s->b4519>4) return 0;
    int32_t input=sh(s->u7206),target=s->d9732[6];
    int32_t filtered=add(s->v1520,sar(sub(target,s->v1520),3));
    unsigned row=0;
    while(row<5&&s->b4549>=(learning_001634[2*row]|((uint16_t)learning_001634[2*row+1]<<8))) ++row;
    if(row>=5) return 0;
    /* 05ADB0 interpolation return is discarded; no state effect. */
    s->v1516=0;s->p1498=(uint8_t)row;s->p1497=0;
    if(s->p1500&1) {
        if(input>=sub(target,128)) s->p1500|=32;
        if(!(s->p1500&32)) {
            if(s->p1499>4) return 0;
            int32_t delta=input-sh(s->v1510),z[2];
            for(unsigned i=0;i<2;++i) z[i]=sar(half(0x1ec4+2*i)*sh(s->v1502),14)+sar(half(0x1ec8+2*i)*sh((uint32_t)delta),14);
            int32_t difference=z[1]-sh(s->v1508);
            s->v1510=(uint16_t)input;s->v1508=(uint16_t)z[1];s->v1502=(uint16_t)z[0];
            int32_t value=clamp(difference+sh(s->v1506),-32768,32767);
            if(difference<half(0x1f40+2*s->p1499)||z[1]<0) value=0;
            else filtered=s->v1520;
            s->v1506=(uint16_t)value;
        }
    }
    s->v1520=filtered;
    int32_t adjusted=add(filtered,s->w7222[s->b4519]);
    int32_t error=clamp(sub(input,adjusted),-16320,16320);
    s->u7106=(uint16_t)sar(sh(s->v1512)+error,1);s->v1512=(uint16_t)error;
    if(!(s->p1500&1)||(s->p1500&16)) return 1;
    if(input>=sub(target,64)&&!(s->p1500&2)) {
        s->p1500=(s->p1500|2u)&~8u;s->b4798=0;s->v1504=0;s->p1496=0;
    }
    if(input>=add(adjusted,128)) {
        if(!(s->p1500&4)) s->b4797=0;
        s->p1500|=4;
        s->v1504=(uint16_t)clamp(sar(sh(s->u7106),3)+sh(s->v1504),-32768,32767);
    } else if((s->p1500&4)&&!(s->p1500&8)) { s->p1496=s->b4797;s->p1500|=8; }
    if((s->p1500&2)&&s->b4798>=byte(0x1ee7)) {
        s->p1500|=16;
        if((s->p1500&4)&&!(s->p1500&8)) { s->p1496=s->b4797;s->p1500|=8; }
    }
    return 1;
}
#define WRAP(name,impl) int name(FactoryLearning *s) { if(!s) return 0;FactoryLearning t=*s;if(!impl(&t)) return 0;*s=t;return 1; }
WRAP(factory_engagement_fill,fill)
WRAP(factory_engagement_edge,edge)
WRAP(factory_engagement_override,override)
WRAP(factory_engagement_step,engagement)
WRAP(factory_learning_up,up)
WRAP(factory_learning_up_observer,up_observer)
WRAP(factory_learning_down,down)
WRAP(factory_learning_down_observer,down_observer)
