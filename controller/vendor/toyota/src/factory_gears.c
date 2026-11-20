#include "gear_internal.h"

static void gear_57bf2(FactoryGearState *s) {
    if (U(7164)>=25600) SET(P(1384),1);
    if (U(7184)>=12800) SET(P(1384),2);
    if (B(4841)&0x50) return;
    CLR(P(1384),4); CLR(B(4835),16);
    if ((B(7159)|B(7193))&16) SET(P(1384),4);
    if ((P(1384)&4)||((B(7125)|B(8677)|B(7419))&16)||(B(5299)&2)||
        !(P(1384)&1)||!(P(1384)&2)||(B(4846)&64)) SET(B(4835),16);
}
static void gear_57d78(FactoryGearState *s) {
    unsigned i=0;
    while (i<3 && U(7154)<ru16(0x13d4+2*i)) ++i;
    B(4526)=(uint8_t)i;
    i=3;while(i && U(7154)<ru16(0x13dc+2*i-2)) --i;
    B(4525)=(uint8_t)i;
}
static void gear_5769a(FactoryGearState *s) {
    int32_t a[2];
    for (unsigned k=0;k<2;++k) {
        uint32_t sum=0;for(unsigned j=0;j<4;++j) sum+=s->periods[j+2*k];
        a[k]=factory_div_s32_s16(0x249f00,(int16_t)sx16(sum>>3));
        if(a[k]<136) a[k]=136;
    }
    int32_t d=cap(sar(factory_div_s32_s16(sx16((uint32_t)(a[0]-a[1]))*a[0],307),2),-128,127);
    B(4527)=(uint8_t)d;
    if ((B(7191)&16)||(B(4844)&4)) B(4765)=0;
    if (!(B(4838)&32)) B(4658)=0;
    if (B(4548)>=40 && B(4852)>=2) SET(P(1372),1);
    if (B(4548)<35) CLR(P(1372),1);
    if (B(4765)<61 || (!(B(4846)&128)&&!(B(4845)&3)) || B(4766)<61 ||
        (U(7202)<=1792 && d<=8) ||
        (B(4658)<24 && d<=rb(0x131c+B(4862))) || B(4658)>=122) {
        CLR(B(4838),32);return;
    }
    if (!(P(1372)&1) && B(4852)<=1 && U(7202)>1792 &&
        d>rb(0x1324+8*B(4852)+B(4862))) SET(B(4838),32);
}
static void gear_57b6a(FactoryGearState *s) {
    if (B(4837)&8) B(4854)=B(4852);
    CLR(B(4837),8);CLR(P(1380),0x43);
}
static void gear_56484(FactoryGearState *s) {
    CLR(B(4840),128);
    if (!(B(5153)&4)||B(4548)>=55||B(4853)>1) SET(B(4840),128);
    CLR(B(4839),1);
    if (!(B(5153)&2)||B(4548)>=70||B(4853)>2) SET(B(4839),1);
    if (!(B(4844)&2)&&B(4854)>=2&&!(B(4840)&128)) B(4854)=1;
    if (B(4854)==3 && ((!(B(4839)&1)&&!(B(4844)&2))||(B(4846)&2)||(B(4845)&1))) --B(4854);
}
static void gear_57c6c(FactoryGearState *s) {
    if (B(4848)==3 && (P(1384)&4) && H(7208)>=12800) B(4854)=3;
    if (B(4848)!=3 && (B(4835)&16) && B(4854)==3) { SET(B(4835),32);--B(4854); }
    else CLR(B(4835),32);
    if (!(B(5722)&1)) B(4756)=0;
    if (B(4756)<122) B(4854)=B(4853);
}
static void gear_5608a(FactoryGearState *s) {
    if (B(4834)&16) B(4774)=0;
    if (B(4854)==B(4853)) return;
    SET(B(4840),1);
    if (B(4854)==B(4852)) { CLR(B(4841),0x90);CLR(B(4840),6);return; }
    if (!(B(4841)&16)) { SET(B(4841),48);B(4775)=0; }
    if (B(4854)>B(4852)) {
        B(4773)=B(4775);SET(B(4840),2);CLR(B(4840),4);
        if (((B(4845)>>6)^(B(4845)>>1))&1 || ((B(4845)>>7)^(B(4845)>>2))&1) B(4773)=255;
    } else {
        B(4773)=B(4774);CLR(B(4841),32);SET(B(4840),4);CLR(B(4840),2);
        if (B(4852)==3) B(4773)=B(4775);
    }
}
static void gear_57cc6(FactoryGearState *s) {
    int32_t hi=3,lo=0;
    if ((B(4838)&2)&&(B(4852)==3||(B(4831)&64))) B(4755)=0;
    if ((B(4840)&2)&&B(4852)==2&&(B(9748)&1)&&!(B(9748)&2)&&(B(4842)&32)&&
        (B(4755)>=8||(B(4843)&4))) hi=2;
    if ((B(4840)&4)&&B(4852)==3) {
        lo=2;
        if (!(B(4842)&128)&&(B(4845)&6)) lo=1;
        if ((B(9748)&1)&&(B(4842)&128)&&(B(4755)>=8||(B(4843)&4))) lo=3;
    }
    if (B(4831)&128) lo=1;
    if (B(4831)&64) lo=2;
    if (hi>sx8(B(4526))) hi=sx8(B(4526));
    if (lo<sx8(B(4525))) lo=sx8(B(4525));
    B(4534)=(uint8_t)hi;B(4535)=(uint8_t)lo;
}
static void gear_56152(FactoryGearState *s) {
    uint8_t n=P(1165);
    if ((B(4841)&128)||!(B(4841)&2)||(B(4841)&1)||(B(7193)&16)||
        H(7204)<sx32(s->d9732[n]-128u)||B(4852)==3||!(B(9748)&2)||
        (P(1166)&2)||n<sx8(B(4535))||n>sx8(B(4534))) return;
    if (B(4854)!=n) {
        SET(B(4841),16);
        if (B(4854)>n) { SET(B(4840),2);SET(B(4841),128);CLR(B(4840),4); }
        else { SET(B(4840),4);CLR(B(4840),2); }
    } else { CLR(B(4840),6);CLR(B(4841),16); }
    B(4852)=n;
}
static uint8_t gear_5641e(FactoryGearState *s) {
    unsigned prev=B(4851),i=prev;
    if (prev==2 && ((B(9748)>>2)&7)==2) ++i;
    if (B(4842)&32) { i=prev+5;if(!prev && B(4862)==7) --i; }
    if (!(B(4840)&2)) {
        i=prev+7;
        if (prev==3) { if(!(B(4842)&128)) i+=2;else if(B(4845)&6) ++i; }
    }
    return rb(0x1124+i);
}
static void gear_561e4(FactoryGearState *s) {
    if (P(1166)&1) SET(P(1166),2);else CLR(P(1166),2);
    if (!(B(4841)&16)||(B(4838)&32)) return;
    /* Each committed iteration moves one index toward a bounded request. */
    for(unsigned iteration=0;iteration<4;++iteration) {
        unsigned old=B(4852),n=old;
        uint8_t count=255,limit=0;
        if (B(4840)&2) {
            if (!(B(4842)&32)) {
                unsigned row=old;uint32_t margin=128;
                if (old<=1) { margin=interp((uint16_t)(B(4549)<<8),0x1110+9*row)>>2;++row; }
                if (H(7204)>=sx32(s->d9732[row]+margin)) {
                    if (old<2&&(P(1166)&1)) CLR(P(1166),1);
                    else { count=0;limit=255; }
                }
                if (B(7193)&16) {
                    count=0;limit=rb(0x110d+old);
                    if (!(B(4842)&64)) count=B(4772);
                }
            } else if (old!=B(4851)||(B(9748)&2)) { count=0;limit=255; }
        }
        if (B(4773)<gear_5641e(s)) return;
        unsigned up=(B(4840)>>1)&1;
        if (!(up && count>=limit) && !(B(4840)&4)) return;
        if (up) { if(sx8(old)>=sx8(B(4534))) return;n=old+1; }
        else { if(-sx8(old)>=sx8((uint32_t)-sx8(B(4535)))) return;n=old-1; }
        /* Domain validation by wrapper requires limits in 0..3. */
        P(1165)=B(4851);B(4852)=(uint8_t)n;CLR(B(4841),128);
        if (B(4852)==B(4854)) { CLR(B(4840),6);CLR(B(4841),16);return; }
    }
}
static void gear_5631a(FactoryGearState *s) {
    if (B(4854)==B(4853)&&B(4852)==B(4851)) return;
    if (!(B(4841)&16)) { SET(B(4841),64);B(4856)=0; }
    else CLR(B(4841),64);
}
static void gear_56348(FactoryGearState *s) {
    int32_t error=H(7204)-sar(H(7208)*J(1168),12);
    unsigned n=B(4852);
    if (B(4842)&32) CLR(P(1166),1);
    else if ((B(4845)&4)||((B(4845)&2)&&n==1)||(B(4842)&64)||n!=B(4851)) {
        V(1168)=(uint16_t)factory_div_s32_s16(H(7204)*4096,(int16_t)H(7208));
        error=H(7204)-sar(H(7208)*J(1168),12);
        CLR(P(1166),1);B(4772)=0;P(1164)=0;
    } else {
        if (n<2 && error>=J(1170)-sx16(ru16(0x110a)) && B(4772)>=rb(0x1108+n)) {
            if(P(1164)<255) ++P(1164);
        } else P(1164)=0;
        if (P(1164)>=rb(0x110c)) SET(P(1166),1);
    }
    V(1170)=(uint16_t)error;
}
static void gear_56408(FactoryGearState *s) {
    if ((B(4841)&64)&&B(4856)==255) CLR(B(4841),64);
}
static int8_t gear_57b8a(FactoryGearState *s) {
    unsigned n=B(4852);int8_t delta=n==3?-2:-1;
    if (B(4845)&2) { n=4;delta=-2; }
    if (B(4845)&4) { n=5;delta=-1; }
    for(unsigned k=0;k<2;++k) {
        uint32_t a=ru32(0xb1e0+4*(n*2+k));
        if(a!=0xb1d4 && H(7186)<sx16(interp(U(7202),a)>>1)) break;
        ++delta;
    }
    return delta;
}
static void gear_57934(FactoryGearState *s) {
    if ((B(7252)&1)||(B(4845)&6)) { CLR(P(1380),0x43);goto apply; }
    CLR(P(1380),1);
    if (U(7202)<ru16(0x1346)&&B(4733)>=rb(0x134c)) {
        CLR(P(1380),2);
        unsigned row=((B(4821)&4)||U(7164)<24320)?1:0;
        if(B(4760)==255&&B(4852)!=0&&H(7186)<sx16(ru16(0x1340+2*row))) {
            SET(P(1380),1);CLR(P(1380),64);
        }
    } else {
        if ((U(7202)>=ru16(0x1348)&&H(7186)<sx16(interp(U(7202),0x1394)>>1)) ||
            gear_57b8a(s)+(int)B(4852)>1 || B(4852)>1) { CLR(P(1380),0x42);goto apply; }
        if(U(7202)>=ru16(0x1346)&&!(B(7252)&32)&&B(4758)!=255) {
            SET(P(1380),2);
            if(!(P(1380)&64)) { SET(P(1380),64);B(4759)=rb(0x134a); }
        }
    }
apply:
    if(P(1380)&1) B(4854)=B(4852)==3?2:0;
    if((P(1380)&2)&&B(4759)==255) B(4854)=1;
}
static void gear_578f0(FactoryGearState *s) {
    if(!(B(4845)&6)&&B(4760)==255) B(4854)=(uint8_t)(gear_57b8a(s)+(int)B(4852));
    gear_57934(s);
}
static void gear_57a3e(FactoryGearState *s) {
    if((B(4845)&4)||!(B(4845)&2)||((B(4845)&64)&&B(4760)!=255)) return;
    int32_t n=sx8((uint32_t)(gear_57b8a(s)+(int)B(4852)));
    B(4854)=(uint8_t)(n<1?1:n);
}
static void gear_57a78(FactoryGearState *s) {
    if((B(4845)&4)&&B(4760)==255) B(4854)=(uint8_t)cap(sx8((uint32_t)(gear_57b8a(s)+(int)B(4852))),0,1);
}
static void gear_57aac(FactoryGearState *s) {
    if(((B(4846)&2)||(B(4845)&1))&&B(4854)>=2) B(4854)=2;
}
static void gear_57ac8(FactoryGearState *s) {
    if(B(4854)!=B(4853)) { SET(B(4840),1);SET(B(4837),8); }
}
static void gear_57ade(FactoryGearState *s) {
    if(!(B(7252)&1)) return;
    B(4852)=0;B(4854)=0;
    if(B(4853)) SET(B(4840),1);else CLR(B(4840),1);
    CLR(B(4837),8);B(4760)=255;
}
static void gear_57b0c(FactoryGearState *s) {
    if(!(B(4837)&8)) return;
    uint8_t n=B(4854);
    if((P(1380)&1)&&!n) B(4758)=rb(0x134b);
    if(sx8(n)<sx8(B(4535))||sx8(n)>sx8(B(4534))) return;
    unsigned row=(B(4851)==2 && n<2 && (B(4845)&6))?1:0;
    B(4852)=n;CLR(B(4837),8);B(4760)=rb(0x1344+row);
}
static int request_maps(FactoryGearState *s) {
    FactoryRequestState q={.load_7202=U(7202),.index_4854=B(4854),.speed_4549=B(4549),
        .flags_4845=B(4845),.flags_4846=B(4846),.flags_4844=B(4844),.flags_7252=B(7252),
        .flags_4839=B(4839),.flags_p1172=P(1172),.counter_4771=B(4771),.override_4862=B(4862)};
    for(unsigned i=0;i<6;++i) q.thresholds_4541[i]=s->thresholds[i];
    if(!factory_request_stage(&q)) return 0;
    B(4854)=q.index_4854;B(4839)=q.flags_4839;P(1172)=q.flags_p1172;B(4771)=q.counter_4771;
    for(unsigned i=0;i<6;++i) s->thresholds[i]=q.thresholds_4541[i];
    return 1;
}
static int gears_step(FactoryGearState *s) {
    gear_57bf2(s);gear_57d78(s);gear_5769a(s);
    if(!(B(4844)&2)) gear_57b6a(s);
    if(!request_maps(s)) return 0;
    gear_56484(s);gear_565ce(s);gear_57c6c(s);gear_5608a(s);gear_57cc6(s);
    gear_56152(s);gear_561e4(s);gear_5631a(s);gear_56348(s);
    if(B(4844)&2) {
        B(4854)=B(4853);B(4852)=B(4851);CLR(B(4840),1);CLR(B(4841),0xf0);B(4856)=255;
        gear_578f0(s);gear_57a3e(s);gear_57a78(s);gear_57aac(s);gear_57c6c(s);
        gear_57ac8(s);gear_57ade(s);gear_57b0c(s);
    }
    return 1;
}
/* Valid bounds also guarantee every iterative transition terminates. The
 * full controller overwrites its limits before using them. */
static int bounded_limits(const FactoryGearState *s) { return B(4534)<=3&&B(4535)<=3; }
#define WRAP(a) int factory_gear_##a(FactoryGearState *p) { \
    if(!valid_gear(p)||!bounded_limits(p)) return 0; \
    FactoryGearState t=*p;gear_##a(&t);if(!valid_gear(&t)) return 0;*p=t;return 1; }
FACTORY_GEAR_ENTRIES(WRAP)
#undef WRAP
int factory_gears_step(FactoryGearState *p) {
    if(!valid_gear(p)) return 0;
    FactoryGearState t=*p;
    if(!gears_step(&t)||!valid_gear(&t)) return 0;
    *p=t;return 1;
}
int factory_gears_outputs_step(FactoryGearState *p,FactoryGearWrites *writes) {
    if(!valid_gear(p)||!writes||p->driver5302[0]>4||p->driver5302[1]>4) return 0;
    FactoryGearState t=*p,*s=&t;
    if(!gears_step(s)||!valid_gear(s)) return 0;
    FactoryShiftOutputState out={.index_4852=B(4852),.index_4850=B(4850),.previous_p1369=P(1369),
        .flags_4838=B(4838),.flags_7189=B(7189),.flags_7187=B(7187),.flags_4845=B(4845),
        .index_4847=B(4847),.value_4533=B(4533),.speed_4548=B(4548),.flags_4844=B(4844),
        .value_4547=B(4547),.flags_p1368=P(1368),.value_4528=B(4528),.index_4848=B(4848),
        .event_p2121=P(2121),.event_p2129=P(2129)};
    for(unsigned i=0;i<4;++i) out.gates_4532[i]=s->gates[i];
    FactoryDriverBatch batch;
    if(!factory_shift_outputs(&out,(int8_t)s->driver5302[0],(int8_t)s->driver5302[1],&batch)) return 0;
    B(4838)=out.flags_4838;P(1369)=out.previous_p1369;P(1368)=out.flags_p1368;
    B(4528)=out.value_4528;B(4848)=out.index_4848;P(2121)=out.event_p2121;P(2129)=out.event_p2129;
    for(unsigned i=0;i<4;++i) s->gates[i]=out.gates_4532[i];
    FactoryGearWrites result={0};
    for(unsigned i=0;i<batch.count;++i) {
        unsigned ch=batch.commands[i].channel;
        if(ch>1) return 0;
        FactoryDriverState d={s->driver5314[ch],s->driver5311[ch],s->driver5308[ch],s->driver5305[ch],s->driver5302[ch]};
        FactoryDriverWrite w;
        if(!factory_driver_dispatch(&d,batch.commands[i].mode,(uint8_t)ch,&w)) return 0;
        s->driver5314[ch]=d.requested_5314;s->driver5311[ch]=d.inhibit_5311;
        s->driver5308[ch]=d.override_5308;s->driver5305[ch]=d.forced_5305;s->driver5302[ch]=d.state_5302;
        if(w.write_pending) result.writes[result.count++]=w;
    }
    *p=t;*writes=result;return 1;
}
#define RETURN_WRAPPER(a,type) int factory_gear_##a(FactoryGearState *p,type *out) { \
    if(!valid_gear(p)||!out) return 0;FactoryGearState t=*p; \
    type v=gear_##a(&t);if(!valid_gear(&t)) return 0;*p=t;*out=v;return 1; }
RETURN_WRAPPER(57b8a,int8_t)
RETURN_WRAPPER(5641e,uint8_t)
RETURN_WRAPPER(567b6,uint8_t)
RETURN_WRAPPER(56b88,uint8_t)
RETURN_WRAPPER(5737e,uint8_t)
int factory_gear_5724c(FactoryGearState *s,uint8_t channel) {
    if(!valid_gear(s)||channel>1) return 0;
    FactoryGearState t=*s;gear_5724c(&t,channel);*s=t;return 1;
}
