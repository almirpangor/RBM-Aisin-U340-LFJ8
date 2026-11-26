#include "factory_torque.h"
#include "factory_core.h"
#include "factory_phase_modes.h"
#include "donor_calibration.h"
#define B(n) (s->b##n)
#define U(n) (s->u##n)
#define P(n) (s->p##n)
#define PHASE(w) ((w)&7u)
#define GEAR(w) (((w)>>3)&3u)
static int32_t sh(uint32_t v) { v&=65535u;return v<32768u?(int32_t)v:(int32_t)v-65536; }
static int32_t sb(uint32_t v) { v&=255u;return v<128u?(int32_t)v:(int32_t)v-256; }
static int32_t sw(uint32_t v) { return v<=0x7fffffffu?(int32_t)v:-1-(int32_t)~v; }
static void phase(uint32_t *w,unsigned p) { *w=(*w&~7u)|p; }
static uint8_t byte(unsigned a) { return torque_00148C[a-0x148c]; }
static uint16_t half(unsigned a) { return (uint16_t)(byte(a)|((uint16_t)byte(a+1)<<8)); }
static int valid(const FactoryTorque *s) {
    if(!s||s->b4852>3||s->b4851>3||s->b4523>3||s->b4545>6||s->b4522>7||s->b4521>7||s->p1417>4) return 0;
    if(GEAR(s->alternate)>2||GEAR(s->downshift)>2) return 0;
    for(unsigned i=0;i<3;++i) if(GEAR(s->queue[i])>2||s->captured7118[i]>255||s->captured7112[i]>255) return 0;
    return 1;
}
/* 058760. Immutable pointer table 00B210 was checked during extraction. */
static uint8_t lookup(const FactoryTorque *s,unsigned slot,unsigned parameter,unsigned gear) {
    static const uint16_t base[11]={0x1510,0x1494,0x15d8,0x14a8,0x14bc,0x157c,0x14d0,0x15ec,0x14e0,0x1500,0x14f0};
    unsigned load=B(4545)?B(4545)-1u:0u,row=0;
    int up=((s->queue[slot]|s->alternate)&32u)!=0;
    unsigned stride=up?6u:5u,q=up?s->captured7118[slot]:s->captured7112[slot];
    unsigned bins=up?0x15fcu:0x1620u;
    while(row+1<stride && q>=half(bins+2*(stride*gear+row))) ++row;
    unsigned i=parameter?row+stride*gear:row+stride*(load+6*gear);
    return byte(base[parameter+(up?0:5)]+i);
}
int factory_torque_lookup(const FactoryTorque *s,unsigned slot,unsigned parameter,unsigned gear,uint8_t *value) {
    if(!valid(s)||slot>2||parameter>5||gear>2||!value) return 0;
    *value=lookup(s,slot,parameter,gear);return 1;
}
static void pop(FactoryTorque *s) {
    for(unsigned i=0;i<2;++i) { s->count4703[i]=s->count4703[i+1];s->queue[i]=s->queue[i+1];
        s->captured7118[i]=s->captured7118[i+1];s->captured7112[i]=s->captured7112[i+1]; }
    s->queue[2]=0;s->captured7118[2]=s->captured7112[2]=0;s->count4703[2]=255;
    if(B(4523)) --B(4523);
}
/* 058276: split a multi-gear transition into at most three pending entries. */
static void enqueue(FactoryTorque *s) {
    unsigned from=B(4851),to=B(4852),count=B(4523);
    while(from!=to) {
        uint32_t previous=s->queue[count?count-1:0],w=1;
        unsigned a=U(7204)>16320?255:U(7204)>>6,b=U(7208)>16320?255:U(7208)>>6;
        if(from<to) {
            w|=32u|((from&3u)<<3);if(count<3) ++count;
            if(!(previous&32)) { count=1;if(PHASE(previous)) phase(&w,2); }
            ++from;
        } else {
            if(from==3&&to==1) { w|=8u|128u;from=1; }
            else { --from;w|=(from&3u)<<3; }
            if(count<3) ++count;
            if(!(previous&32)) { if(PHASE(previous)<2) count=1; }
            else { phase(&w,2);count=1;if(GEAR(w)==2) w|=0x800u; }
        }
        s->queue[count-1]=w;s->captured7118[count-1]=(uint16_t)a;s->captured7112[count-1]=(uint16_t)b;s->count4703[count-1]=0;
    }
    if((B(4841)&128)||(s->queue[0]&0x800u)) count=0;
    for(unsigned i=count;i<3;++i) { s->queue[i]=0;s->captured7118[i]=s->captured7112[i]=0;s->count4703[i]=255; }
    B(4523)=(uint8_t)count;
}
static void activate(FactoryTorque *s,unsigned slot) {
    uint32_t w=s->queue[slot];unsigned g=GEAR(w);int fire=0;
    if(w&32) fire=(B(4843)&4)&&sh(U(7158))<0;
    else { int32_t limit=sw(s->targets[g]-(uint32_t)(lookup(s,0,5,g)<<6));
        fire=sh(U(7204))>limit&&sh(U(7158))>0; }
    if(fire) { phase(&w,3);B(4700)=0; }s->queue[slot]=w;
}
static void finish(FactoryTorque *s) {
    uint32_t w=s->queue[0];unsigned g=GEAR(w);int end=0;
    if(w&32) {
        int32_t limit=sw(s->targets[g+1]+(uint32_t)(lookup(s,0,3,g)<<6));
        end=sh(U(7204))<limit&&sh(U(7158))<0;
    } else {
        int32_t limit=sw(s->targets[g]-(uint32_t)sh(half(0x148c+2*g)));
        if(!(w&0x100u)&&sh(U(7204))>limit&&sh(U(7158))>0) { w|=0x100u;B(4700)=0;s->queue[0]=w; }
        if((w&0x100u)&&B(4700)>=lookup(s,0,4,g)) end=1;
    }
    if(end) {
        phase(&w,4);s->queue[0]=w;
        if(!(B(4833)&2)) { B(4807)=0;int32_t n=sb((uint32_t)lookup(s,0,0,g)-1);P(1400)=(uint8_t)(n<0?0:n); }
        else P(1400)=0;
    }
}
/* Shared exact signed-halfword ramp at 05865A and 058A1E. */
static uint8_t speed_ramp(int32_t delta,unsigned floor,unsigned initial,uint16_t *memory,unsigned count,unsigned old) {
    int16_t step=factory_div_s32_s16(sh(initial)-(int32_t)(floor<<4),(int16_t)count);
    while(old>1) { int32_t next=sh((uint32_t)(sh(*memory)-step));if(next<sh((uint32_t)delta)) break;--old;*memory=(uint16_t)next; }
    return sh((uint32_t)delta)<sh(floor<<4)?0:(uint8_t)old;
}
static uint8_t timed_ramp(unsigned counter,unsigned duration,unsigned initial,unsigned old) {
    uint32_t left=256u-factory_div_u32_u16(counter<<8,(uint16_t)duration);
    unsigned result=(uint8_t)(((left*initial&65535u)+255u)>>8);
    if(result>old) result=old;return (uint8_t)(counter>=duration?0:result);
}
static void tail(FactoryTorque *s) {
    uint32_t w=s->queue[0];unsigned p=PHASE(w),g=GEAR(w),level=lookup(s,0,0,g);
    if(p==4&&level) {
        if(w&32) {
            int32_t delta=sw((uint32_t)sh(U(7206))-s->targets[g+5]);if(delta>32767) delta=32767;
            unsigned floor=lookup(s,0,4,g);
            if(!(w&0x200u)) { s->queue[0]=w|0x200u;P(1402)=P(1404)=(uint16_t)delta;level=P(1400); }
            else level=speed_ramp(delta,floor,P(1404),&P(1402),P(1400),B(4522));
            if(sh((uint32_t)delta)<sh(floor<<4)) level=0;
        } else level=timed_ramp(B(4807),lookup(s,0,3,g),P(1400),B(4522));
    }
    B(4833)&=(uint8_t)~4u;
    if(!((B(4846)&128)||(B(4845)&7)) || (B(4846)&32)||(B(5139)&2)||B(4548)<10||(B(4844)&2)||!B(4545)) B(4833)|=4;
    w=s->queue[0];
    int gate=((w&32)?(B(4842)&2):(B(4842)&8))!=0;
    if(!p||!gate||(w&128)||(B(4833)&4)) level=0;
    B(4522)=(uint8_t)level;
}
static void main_queue(FactoryTorque *s) {
    enqueue(s);B(4833)&=(uint8_t)~2u;
    for(int i=(int)B(4523)-1;i>=0;--i) {
        unsigned g=GEAR(s->queue[i]);
        if(s->count4703[i]>=lookup(s,(unsigned)i,1,g))
            for(int j=i;j>=0;--j) if(PHASE(s->queue[j])==1) phase(&s->queue[j],2);
        if(PHASE(s->queue[i])==2) {
            activate(s,(unsigned)i);
            if(PHASE(s->queue[i])==3) { while(i>0) { pop(s);--i; }B(4841)&=(uint8_t)~32u;B(4833)|=2; }
        }
    }
    if(PHASE(s->queue[0])==3) finish(s);
    tail(s);unsigned level=B(4522),g=GEAR(s->queue[0]);
    if(s->count4703[0]>=lookup(s,0,2,g)||(PHASE(s->queue[0])==4&&!level)) { level=0;pop(s); }
    B(4522)=(uint8_t)level;B(4834)&=(uint8_t)~128u;
    if(PHASE(s->queue[0])>=3&&level) B(4834)|=128;
}
static void alternate_tail(FactoryTorque *s) {
    uint32_t w=s->alternate;unsigned g=GEAR(w),load=B(4545)?B(4545)-1u:0u;
    unsigned level=byte(0x1640+6*g+load);
    if(PHASE(w)==4&&level) {
        unsigned current=B(4852);
        int32_t delta=sw((uint32_t)sh(U(7206))-s->targets[current+4]);if(delta>32767) delta=32767;
        unsigned floor=lookup(s,0,4,g);
        if(!(w&0x200u)) { w|=0x200u;P(1410)=P(1412)=(uint16_t)delta;level=P(1408); }
        else level=speed_ramp(delta,floor,P(1412),&P(1410),P(1408),B(4521));
        if(sh((uint32_t)delta)<sh(floor<<4)) level=0;
    }
    if((B(4833)&4)||!(B(4842)&2)) level=0;
    if(PHASE(w)>=3) B(4521)=(uint8_t)level;s->alternate=w;
}
static void alternate(FactoryTorque *s) {
    uint32_t w=s->alternate;unsigned current=B(4852),g=current?current-1u:0u;
    unsigned load=B(4545)?B(4545)-1u:0u;
    if((B(9748)&3)==3&&!(B(4841)&128)) {
        int same=B(4851)==current;
        if((same&&!(B(4842)&4)&&(B(4842)&2)) || (!same&&!(B(4842)&64)&&(B(4842)&32))) {
            w=(w&~31u)|3u|(g<<3)|32u;B(4841)&=(uint8_t)~32u;B(4833)|=2;
        }
    } else w=0;
    int32_t limit=sw(s->targets[current]+(uint32_t)(lookup(s,0,3,GEAR(w))<<6));
    if(sh(U(7204))<limit) {
        if(PHASE(w)==3) { int32_t n=sb((uint32_t)byte(0x1640+6*GEAR(w)+load)-1);P(1408)=(uint8_t)(n<0?0:n);phase(&w,4); }
    } else if(PHASE(w)==4) { phase(&w,3);w&=~0x200u; }
    s->alternate=w;alternate_tail(s);w=s->alternate;unsigned level=B(4521);
    if(PHASE(w)==4&&!level) { w=0;B(4833)&=(uint8_t)~64u; }
    if(PHASE(w)>=3) { B(4521)=(uint8_t)level;B(4833)=(B(4833)|32u)&~64u;if(level) B(4833)|=64; }
    s->alternate=w;
}
static void down_tail(FactoryTorque *s) {
    uint32_t w=s->downshift;unsigned level=byte(0x1658+P(1417));
    if(PHASE(w)==4&&level) level=timed_ramp(B(4805),byte(0x1660+P(1417)),P(1416),B(4521));
    if((B(4833)&4)||!(B(4842)&8)) level=0;
    if(PHASE(w)>=3) B(4521)=(uint8_t)level;
}
static int down(FactoryTorque *s) {
    uint32_t w=s->downshift;unsigned mode=(B(9748)>>2)&7u;
    if(!(B(4841)&128)&&(B(9748)&1)&&!(B(9748)&2)&&(mode==2||mode==4)) {
        if(PHASE(w)!=3&&sh(U(7106))>=sh(half(0x1654))) {
            w=(w&~31u)|19u;unsigned row=0;
            /* Five bins including immutable 65535 sentinel; captured<=255. */
            while(row<5&&s->captured7112[0]>=half(0x1634+2*row)) ++row;
            if(row>=5) return 0;
            P(1417)=(uint8_t)row;B(4841)&=(uint8_t)~32u;B(4833)|=2;
        }
    } else w=0;
    if(PHASE(w)==3&&sh(U(7106))<sh(half(0x1656))) {
        int32_t n=sb((uint32_t)byte(0x1658+P(1417))-1);B(4805)=0;P(1416)=(uint8_t)(n<0?0:n);phase(&w,4);
    }
    s->downshift=w;down_tail(s);w=s->downshift;unsigned level=B(4521);
    if(PHASE(w)==4&&!level) { w=0;B(4833)&=(uint8_t)~64u; }
    if(PHASE(w)>=3) { B(4521)=(uint8_t)level;B(4833)=(B(4833)|32u)&~64u;if(level) B(4833)|=64; }
    s->downshift=w;return 1;
}
static void output(FactoryTorque *s) {
    unsigned level=B(4522),active=(B(4834)>>7)&1u;
    if(B(4833)&32) { level=B(4521);active=(B(4833)>>6)&1u; }
    B(4520)=(uint8_t)level;int32_t magnitude=sb(byte(0x1668+level))*32;
    U(7104)=(uint16_t)-magnitude;P(1420)=(uint16_t)magnitude;
    B(4833)=(B(4833)&~16u)|(active?16u:0u);
}
/* Explicit wrappers retain the original destination pointer through copy. */
#define WRAP(name,statement) int name(FactoryTorque *p) { if(!valid(p)) return 0;FactoryTorque t=*p,*s=&t;statement;if(!valid(s)) return 0;*p=t;return 1; }
WRAP(factory_torque_58162,main_queue(s))
WRAP(factory_torque_58276,enqueue(s))
WRAP(factory_torque_5841e,pop(s))
WRAP(factory_torque_58522,finish(s))
WRAP(factory_torque_585f0,tail(s))
WRAP(factory_torque_5883e,alternate(s))
WRAP(factory_torque_589a2,alternate_tail(s))
WRAP(factory_torque_58a92,if(!down(s)) return 0)
WRAP(factory_torque_58bb0,down_tail(s))
WRAP(factory_torque_58c30,output(s))
WRAP(factory_torque_step,B(4833)&=(uint8_t)~32u;main_queue(s);alternate(s);if(!down(s)) return 0;output(s))
int factory_torque_5849a(FactoryTorque *p,unsigned slot) {
    if(!valid(p)||slot>2) return 0;FactoryTorque t=*p;activate(&t,slot);if(!valid(&t)) return 0;*p=t;return 1;
}
void factory_donor_engine_gate(FactoryDonorEngineGate *s) {
    const uint8_t *t=torque_engine_0054F4;
    int32_t release=sh(t[0]|((uint32_t)t[1]<<8));
    int32_t threshold1=sh(t[2]|((uint32_t)t[3]<<8)),hysteresis1=sh(t[4]|((uint32_t)t[5]<<8));
    int32_t threshold2=sh(t[6]|((uint32_t)t[7]<<8)),hysteresis2=sh(t[8]|((uint32_t)t[9]<<8));
    if(sh(s->input8946)>=threshold1&&sh(s->input9418)>=threshold2) s->accepted5138=1;
    if(sh(s->input8946)<sh((uint32_t)(threshold1-hysteresis1))||sh(s->input9418)<sh((uint32_t)(threshold2-hysteresis2))) s->accepted5138=0;
    int32_t next=sh((uint32_t)(release+sh(s->previous8378)));if(next>0) next=0;
    if((s->flags5140&16)&&s->accepted5138==1&&!(s->flags5139&2)&&next>sh(s->request8380)) next=sh(s->request8380);
    s->previous8378=(uint16_t)next;
}
