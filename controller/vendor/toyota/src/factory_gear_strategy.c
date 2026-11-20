#include "gear_internal.h"

void gear_571e2(FactoryGearState *s) {
    CLR(P(1327),14);CLR(B(4839),20);CLR(P(1325),6);
    B(4716)=B(4720)=B(4717)=B(4721)=0;
}
void gear_57210(FactoryGearState *s) {
    CLR(B(4839),8);CLR(P(1326),7);B(4719)=B(4718)=B(4715)=0;
}
void gear_5715e(FactoryGearState *s) {
    ++P(1322);
    if(P(1322)<16) return;
    for(unsigned i=0;i<32;++i) s->samples[i]=s->history[i];
    SET(P(1324),1);P(1322)=0;
}
void gear_571b4(FactoryGearState *s) {
    for(unsigned i=31;i>0;--i) s->history[i]=s->history[i-1];
    s->history[0]=s->periods[0];
}
void gear_5722e(FactoryGearState *s) { for(unsigned i=0;i<32;++i) s->history[i]=65535; }
void gear_57074(FactoryGearState *s) {
    ++P(1323);if(P(1323)<16) return;
    int32_t value=0;
    unsigned gear=B(4853);
    if(gear>=2) {
        uint32_t table=((B(4828)&128)||(B(4827)&1))?0x1188:0x1154;
        value=sx16((uint32_t)((interp(factory_period_raw(U(7166)),table+25*(gear-2))>>5)-800));
        if(!(B(4844)&128)) {
            value=cap((int32_t)U(7154)-6400,-6400,32767);
            value=sar(sx16((uint32_t)value)*sx16(ru16(0x11bc+2*gear)),8);
            int32_t ratio=factory_div_s32_s16(sx16(ru16(0xd08+2*gear))*16384,8950);
            uint32_t weighted=(uint32_t)(sx16((uint32_t)value)*ratio);
            weighted-=(uint32_t)interp((uint16_t)(B(4548)<<8),0x11c8)*1024u;
            value=factory_div_s32_s16(sx32(weighted),9650);
            value=sx16((uint32_t)sar(value*25,9));
        }
        if(!(B(4841)&0x50)) {
            int32_t delta=value-J(1340);
            if(delta) { int32_t step=sar(delta,4);if(!step) step=delta<0?-1:1;delta=step; }
            value=J(1340)+delta;
        }
    }
    V(1340)=(uint16_t)value;P(1323)=0;
}
void gear_5724c(FactoryGearState *s,unsigned channel) {
    uint32_t total=0;uint16_t a[2];
    for(unsigned i=0;i<2;++i) {
        uint32_t p=s->v1304[2*channel+i];
        if(p>32767||B(4548)>=135) { a[0]=a[1]=0;total=65535;break; }
        a[i]=factory_div_u32_u16(ru32(0xb198+4*channel),(uint16_t)p);total+=p;
    }
    /* MULHI uses the low signed halfword of the difference. */
    int32_t input=cap(factory_div_s32_s16(sx16((uint32_t)a[0]-a[1])*9958,
                    (int16_t)sx16(total>>1)),-2000,2000);
    int32_t acc=sx16((uint32_t)(sx16(s->v1360[2*channel])+input));
    uint32_t weighted=0;
    for(unsigned i=0;i<2;++i) {
        acc=sx16((uint32_t)(acc+sx16(s->v1360[2*channel+i])));
        weighted+=(uint32_t)(sx16(s->v1352[2*channel+i])*sx16(ru16(0xb1a8+2*(3*channel+i))));
    }
    s->v1360[2*channel+1]=s->v1360[2*channel];s->v1360[2*channel]=(uint16_t)input;
    s->v1352[2*channel+1]=s->v1352[2*channel];
    weighted+=(uint32_t)(acc*sx16(ru16(0xb1ac+6*channel)));
    s->v1352[2*channel]=(uint16_t)sar(sx32(weighted),14);
}
void gear_56eda(FactoryGearState *s) {
    for(unsigned k=0;k<2;++k) for(unsigned row=0;row<2;++row) {
        uint32_t total=0;
        for(unsigned j=0;j<4;++j) {
            uint32_t sum=0;
            for(unsigned i=0;i<=3*k;++i) sum+=s->samples[(3*k+1)*(4*row+j)+i];
            total+=sum>65535?65535:sum;
        }
        s->v1304[2*k+row]=total>>2;
    }
    gear_5724c(s,0);gear_5724c(s,1);
    int32_t w=sx16(interp((uint16_t)(B(4548)<<8),0xb1a0));
    uint32_t mix=(uint32_t)(w*sx16(s->v1352[0]))+
                 (uint32_t)(sx16((uint32_t)(16384-w))*sx16(s->v1352[2]));
    V(1338)=(uint16_t)cap(sar(sx32(mix),20),-200,400);
    uint32_t sum=0;for(unsigned i=0;i<4;++i) sum+=s->samples[i];
    sum>>=1;if(sum>65535) sum=65535;
    uint32_t new_value=(uint32_t)factory_div_u32_u16(0x1232f8adu,(uint16_t)sum)*2;
    int32_t derivative=sar(sx32(new_value-s->v1344[1]),1);
    if(B(4548)>=135) derivative=0;
    derivative=cap(derivative,-2000,2000);
    s->v1344[1]=s->v1344[0];s->v1344[0]=new_value;
    int32_t divisor=sx16(interp((uint16_t)(B(4548)<<8),0x12e4)>>8);
    int32_t value=factory_div_s32_s16(sx16((uint32_t)(J(1336)*4))*sx16((uint32_t)(divisor-1))+
                                    derivative,(int16_t)divisor);
    V(1336)=(uint16_t)cap(sar(value,2),-200,400);
}

uint8_t gear_567b6(FactoryGearState *s) {
    uint8_t request=B(4854);
    if(H(7196)>=2560) B(4726)=0;
    if(!(P(1327)&1)||B(4548)<15||B(4548)>=130||(B(4846)&1)) {
        gear_571e2(s);return request;
    }
    int normal=!(B(4845)&6),drop2=0,drop1=0,high=0,qualified=0;
    if(request<B(4853)&&(B(4842)&128)) { if(request==2) drop2=1;else drop1=1; }
    int32_t threshold;
    if(!normal||request<2) { CLR(P(1327),8);goto reset4721; }
    high=1;
    if((B(4841)&0x50)||B(4662)<31||B(4724)<85) goto reset4721;
    qualified=1;
    threshold=sx16((uint32_t)(sar(J(1340),2)-(interp(U(7208),(P(1327)&8)?0x11f4:0x11dc)>>8)));
    if(!(P(1327)&8)) {
        if(J(1338)>=threshold||B(4726)<61) goto reset4721;
        if(B(4721)>=98) SET(P(1327),8);
    } else {
        if(J(1338)<threshold||B(4725)<153) goto reset4721;
        if(B(4721)>=98) CLR(P(1327),8);
    }
    goto latch_a;
reset4721: B(4721)=0;
latch_a:
    if(drop1&&((P(1325)&64)||(P(1327)&64))) SET(P(1327),4);
    threshold=sar(J(1340),2)-(interp(U(7208),0x11f4)>>8);
    if(qualified && J(1338)>=threshold && B(4725)>=153) {
        if(B(4717)>=98) CLR(P(1327),4);
    } else B(4717)=0;
    if(!normal||drop2) SET(P(1327),2);
    if(normal&&request>=2 && (
        (!(B(7252)&32)&&((!(B(4844)&8)&&(P(1327)&2))||(P(1326)&32))&&(P(1327)&8)) ||
        (P(1327)&4))) SET(B(4839),4);

    if(!high) { CLR(P(1325),2);goto reset4720; }
    if(!qualified) goto reset4720;
    threshold=sx16((uint32_t)(sar(J(1340),2)-(interp(U(7208),(P(1325)&2)?0x1224:0x120c)>>8)));
    if(!(P(1325)&2)) {
        if(J(1338)>=threshold||B(4726)<61) goto reset4720;
        if(B(4720)>=49) SET(P(1325),2);
    } else {
        if(J(1338)<threshold||B(4725)<153) goto reset4720;
        if(B(4720)>=31) CLR(P(1325),2);
    }
    goto latch_b;
reset4720: B(4720)=0;
latch_b:
    if(drop1&&(P(1325)&0xa0)) SET(P(1325),4);
    threshold=sar(J(1340),2)-(interp(U(7208),0x1224)>>8);
    if(qualified&&J(1338)>=threshold&&B(4725)>=153) {
        if(B(4716)>=31) CLR(P(1325),4);
    } else B(4716)=0;
    if(normal&&request>=2 && (
        (!(B(7252)&32)&&!(B(4844)&8)&&!(B(4828)&128)&&!(B(4827)&1)&&(P(1325)&2)&&B(4852)==3) ||
        (P(1325)&4))) SET(B(4839),16);
    if(B(4839)&4) {
        SET(P(1327),16);
        if((P(1327)&12)||(B(7252)&32)) { CLR(P(1327),48);B(4661)=179; }
        if(P(1327)&16) {
            if((B(4844)&8)&&!(P(1327)&32)) { SET(P(1327),32);B(4661)=102; }
            if(B(4661)==255) CLR(B(4839),4);
        }
    }
    if(B(4839)&16) {
        SET(P(1325),8);
        if((P(1325)&6)||(B(7252)&32)||U(7202)<2560) { CLR(P(1325),24);B(4660)=240; }
        if(P(1325)&8) {
            if((B(4844)&8)&&!(P(1325)&16)) { SET(P(1325),16);B(4660)=102; }
            if(B(4660)==255) CLR(B(4839),16);
        }
    }
    if(request==3&&(B(4839)&4)) --request;
    if(!(B(4839)&4)&&((P(1327)&64)||B(4854)==3)) CLR(P(1327),2);
    return request;
}

uint8_t gear_56b88(FactoryGearState *s) {
    uint8_t request=B(4854);
    if(!(P(1327)&1)||B(4548)<15||B(4548)>=130||(B(4846)&1)) {
        gear_57210(s);return request;
    }
    uint16_t load_threshold=interp(U(7208),0x12b4);
    int normal=!(B(4845)&6),qualified=0;
    int32_t value=J(1338),threshold;
    unsigned current_bit=B(4827)&1;
    if(!normal||request<2||
        (current_bit!=((P(1326)>>7)&1)&&!(B(4839)&8))) { CLR(P(1326),2);goto reset4719; }
    if((B(4841)&0x50)||B(4662)<31||B(4659)<31) goto reset4719;
    qualified=1;
    uint32_t table=(P(1326)&2)?(current_bit?0x1284:0x126c):(current_bit?0x1254:0x123c);
    threshold=sx16((uint32_t)(sar(J(1340),2)+(interp(U(7208),table)>>8)));
    if(!(P(1326)&2)) {
        if(value<threshold||B(4723)<49) goto reset4719;
        if((B(4827)&1)&&(H(7128)<=-256||H(7128)>0||B(4722)<18)) goto reset4719;
        if(B(4719)>=49) SET(P(1326),2);
    } else {
        if(!(B(4844)&8)&&U(7202)>=load_threshold) CLR(P(1326),2);
        if(value>=threshold||!(B(4844)&8)||B(4724)<85) goto reset4719;
        if(B(4719)>=31) CLR(P(1326),2);
    }
    goto second;
reset4719: B(4719)=0;
second:
    if(!normal||request<2||B(4723)>=49) { CLR(P(1326),4);goto reset4718; }
    if((B(4841)&0x50)||B(4662)<31||B(4725)<153||B(4659)<31) goto reset4718;
    threshold=sx16((uint32_t)(sar(J(1340),2)+(interp(U(7208),0x12cc)>>8)));
    if(!(P(1326)&4)) {
        if(value<threshold+5||request!=3) goto reset4718;
        if(B(4718)>=49) SET(P(1326),4);
    } else {
        if(request!=3) CLR(P(1326),4);
        if(value>=threshold) goto reset4718;
        if(B(4718)>=31) CLR(P(1326),4);
    }
    goto third;
reset4718: B(4718)=0;
third:
    if((!normal&&!(B(4845)&0xc0)&&((P(1325)&1)||(P(1326)&32))) ||
       ((B(7252)&32)&&B(4813)!=0&&U(7202)<768&&(P(1326)&4))) SET(P(1326),1);
    if(qualified) {
        if(!(B(4844)&8)&&U(7202)>=load_threshold) CLR(P(1326),1);
        threshold=sar(J(1340),2)+(interp(U(7208),0x126c)>>8);
        if(value<threshold&&(B(4844)&8)&&B(4724)>=85) {
            if(B(4715)>=31) CLR(P(1326),1);
        } else B(4715)=0;
    } else B(4715)=0;
    if(normal&&request>=2 && (
        ((((B(7252)&32)&&B(4813)!=0&&(B(4844)&8))||(P(1327)&64))&&(P(1326)&2)) ||
        (P(1326)&1))) SET(B(4839),8);
    if(B(4839)&8) {
        SET(P(1326),8);
        if((P(1326)&3)||(B(7252)&32)) { CLR(P(1326),24);B(4661)=102; }
        if(P(1326)&8) {
            if(U(7202)>=load_threshold&&!(P(1326)&16)) { SET(P(1326),16);B(4661)=194; }
            if(B(4661)==255&&(!(B(4844)&8)||rb(0x114c)==1)) CLR(B(4839),8);
        }
    }
    if(request==3&&(B(4839)&8)) --request;
    return request;
}

uint8_t gear_5737e(FactoryGearState *s) {
    uint8_t request=B(4854);
    if((B(7252)&32)||(B(4844)&8)) B(4634)=0;
    if(H(7196)<sx16(ru16(0x1144))) B(4770)=0;
    if(H(7196)<sx16(ru16(0x1146))) B(4714)=0;
    if((B(4844)&8)||H(7196)>=sx16(ru16(0x114a))) B(4769)=0;
    int32_t threshold=sar(J(1340),2)-(interp(U(7208),0x1310)>>8)+64;
    if(J(1338)<threshold) B(4768)=0;
    if((B(7252)&32)&&!(B(7250)&32)) { V(1328)=V(1336);P(1321)=B(4548); }
    if(!(P(1327)&1)||(B(4846)&1)) { CLR(P(1324),28);goto finish; }
    CLR(P(1324),8);
    if((P(1324)&16)&&(B(7252)&32)) SET(P(1324),4);
    unsigned row=(P(1324)&4)?1:0;
    if(B(4768)<rb(0x1151)||B(4634)<rb(0x1148+row)) goto finish;
    if(B(4634)<=rb(0x114f)&&B(4769)<rb(0x1150)) goto finish;
    CLR(P(1324),20);
finish:
    if(P(1320)<=2) CLR(P(1324),28);
    V(1330)=V(1332);V(1332)=V(1338);CLR(B(4839),32);
    if(request==3&&(P(1324)&28)) { SET(B(4839),32);--request; }
    return request;
}
static void copybit(uint8_t *dst,unsigned d,uint8_t src,unsigned b) {
    *dst=(uint8_t)((*dst&~(1u<<d))|(((src>>b)&1u)<<d));
}
void gear_565ce(FactoryGearState *s) {
    if(H(7196)<-1280) B(4725)=0;
    if(!(B(4844)&8)) B(4723)=0;
    if(B(7252)&32) B(4724)=0;
    if(B(4841)&64) B(4662)=0;
    if(((B(4828)>>7)&1)!=((P(1326)>>6)&1)||(B(4827)&1)!=((P(1326)>>7)&1)) B(4659)=0;
    if(!(B(8880)&1)) B(4722)=0;
    if((B(7252)&32)&&!(B(7250)&32)) V(1334)=V(1336);
    if(B(4852)!=3||!(B(7252)&32)||J(1334)-J(1336)<sx16(interp(U(7208),0x129c)>>7)-64) B(4813)=0;
    if(U(7164)>=25600) SET(P(1327),128);
    if(P(1324)&1) { CLR(P(1324),1);gear_56eda(s); }
    CLR(P(1327),1);
    if(!(B(7252)&1)&&!(B(4845)&1)&&(P(1327)&128)&&!(B(4844)&4)&&
       !((B(7191)|B(7189)|B(7187))&16)&&!((B(5297)|B(5299))&2)&&!(B(4846)&64)) SET(P(1327),1);
    uint8_t first=gear_567b6(s),second=gear_56b88(s);
    if((B(4839)&4)&&!(P(1327)&64)) gear_57210(s);
    if((B(4839)&8)&&!(P(1326)&32)) gear_571e2(s);
    P(1320)=B(4854);
    if(B(4839)&4) B(4854)=first;
    if(B(4839)&8) B(4854)=second;
    B(4854)=gear_5737e(s);
    copybit(&P(1327),6,B(4839),2);copybit(&P(1326),5,B(4839),3);
    copybit(&P(1325),6,P(1327),3);copybit(&P(1325),0,P(1326),1);
    copybit(&P(1325),7,P(1325),1);copybit(&P(1325),5,B(4839),4);
    copybit(&P(1326),6,B(4828),7);copybit(&P(1326),7,B(4827),0);
}
