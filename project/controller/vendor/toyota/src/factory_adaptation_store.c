#include "factory_adaptation_store.h"
#include "donor_calibration.h"
static const uint8_t donor[32]={0xa3,0xcd,0x72,0x3e,0x7e,0x21,0xbf,0x54,0x7c,0xa4,0xc1,0x7e,0xc4,0x9a,0x1e,0x09,0x8d,0x20,0x37,0x73,0x54,0x7d,0xba,0x4d,0x7a,0xf2,0x19,0x91,0xa2,0xcb,0xea,0xd1};
static uint32_t get(const uint8_t *p) { return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void put(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(8*i)); }
static int equal(const uint8_t *a,const uint8_t *b,unsigned n) { for(unsigned i=0;i<n;++i) if(a[i]!=b[i]) return 0;return 1; }
static uint32_t crc(const uint8_t *p,unsigned n) {
    uint32_t c=0xffffffffu;
    for(unsigned i=0;i<n;++i) { c^=p[i];for(unsigned j=0;j<8;++j) c=(c>>1)^((c&1)?0xedb88320u:0); }
    return ~c;
}
static int8_t signed_byte(uint8_t b) { return (int8_t)(b<128?(int)b:(int)b-256); }
void factory_adaptation_capture(const FactoryLearning *s,FactoryAdaptation *a) {
    for(unsigned i=0;i<2;++i) { a->learned_flags[i]=s->learned4619[i];a->down_counts[i]=s->count4594[i]; }
    for(unsigned i=0;i<6;++i) a->up_counts[i]=s->count4600[i];
    for(unsigned i=0;i<18;++i) a->up[i]=s->learned4579[i];
    for(unsigned i=0;i<5;++i) a->down[i]=s->learned4554[i];
    a->down_seen=s->b4603;
}
void factory_adaptation_apply(FactoryLearning *s,const FactoryAdaptation *a) {
    for(unsigned i=0;i<2;++i) { s->learned4619[i]=a->learned_flags[i];s->count4594[i]=a->down_counts[i]; }
    for(unsigned i=0;i<6;++i) s->count4600[i]=a->up_counts[i];
    for(unsigned i=0;i<18;++i) s->learned4579[i]=a->up[i];
    for(unsigned i=0;i<5;++i) s->learned4554[i]=a->down[i];
    s->b4603=a->down_seen;
}
int factory_adaptation_valid(const FactoryAdaptation *a) {
    if(!a) return 0;
    /* LearnedFlags is shared with further OEM adaptation paths; preserve all
     * bits until the whole controller is integrated, rather than clearing them. */
    for(unsigned i=0;i<18;++i) {
        int lo=signed_byte(learning_001C3C[0x1d2c-0x1c3c+i]);
        int hi=signed_byte(learning_001C3C[0x1d18-0x1c3c+i]);
        if(a->up[i]<lo||a->up[i]>hi) return 0;
    }
    for(unsigned i=0;i<5;++i) if(a->down[i]<-40||a->down[i]>40) return 0;
    return 1;
}
static void pack(uint8_t *p,const FactoryAdaptation *a) {
    for(unsigned i=0;i<2;++i) p[i]=a->learned_flags[i];
    for(unsigned i=0;i<6;++i) p[2+i]=a->up_counts[i];
    for(unsigned i=0;i<2;++i) p[8+i]=a->down_counts[i];
    for(unsigned i=0;i<18;++i) p[10+i]=(uint8_t)a->up[i];
    for(unsigned i=0;i<5;++i) p[28+i]=(uint8_t)a->down[i];
    p[33]=a->down_seen;
}
static void unpack(const uint8_t *p,FactoryAdaptation *a) {
    for(unsigned i=0;i<2;++i) a->learned_flags[i]=p[i];
    for(unsigned i=0;i<6;++i) a->up_counts[i]=p[2+i];
    for(unsigned i=0;i<2;++i) a->down_counts[i]=p[8+i];
    for(unsigned i=0;i<18;++i) a->up[i]=signed_byte(p[10+i]);
    for(unsigned i=0;i<5;++i) a->down[i]=signed_byte(p[28+i]);
    a->down_seen=p[33];
}
int factory_adaptation_encode(uint8_t *r,const FactoryAdaptation *a,uint32_t generation) {
    if(!r||!factory_adaptation_valid(a)) return 0;
    for(unsigned i=0;i<FACTORY_ADAPT_RECORD_BYTES;++i) r[i]=0;
    r[0]='U';r[1]='F';r[2]='L';r[3]='1';put(r+4,generation);r[8]=1;r[10]=34;
    for(unsigned i=0;i<32;++i) r[12+i]=donor[i];
    put(r+44,FACTORY_ADAPT_PROFILE_E4R21);pack(r+48,a);put(r+88,crc(r,88));put(r+92,0xa55a3cc3u);
    return 1;
}
int factory_adaptation_decode(const uint8_t *r,FactoryAdaptation *a,uint32_t *generation) {
    if(!r||!a||!generation||r[0]!='U'||r[1]!='F'||r[2]!='L'||r[3]!='1'||
        r[8]!=1||r[9]||r[10]!=34||r[11]||!equal(r+12,donor,32)||
        get(r+44)!=FACTORY_ADAPT_PROFILE_E4R21||get(r+92)!=0xa55a3cc3u||get(r+88)!=crc(r,88)) return 0;
    for(unsigned i=82;i<88;++i) if(r[i]) return 0;
    FactoryAdaptation value;unpack(r+48,&value);if(!factory_adaptation_valid(&value)) return 0;
    *a=value;*generation=get(r+4);return 1;
}
int factory_adaptation_load(const uint8_t *r0,const uint8_t *r1,FactoryAdaptation *a,uint32_t *g) {
    if(!a||!g) return -1;
    FactoryAdaptation a0,a1;uint32_t g0=0,g1=0;
    int v0=factory_adaptation_decode(r0,&a0,&g0),v1=factory_adaptation_decode(r1,&a1,&g1);
    if(!v0&&!v1) return -1;
    if(v0&&v1&&g1-g0==0x80000000u) return -1;
    if(v1&&(!v0||(g1!=g0&&g1-g0<0x80000000u))) { *a=a1;*g=g1;return 1; }
    *a=a0;*g=g0;return 0;
}
int factory_adaptation_save(const FactoryAdaptation *a,int idle,FactoryAdaptRead read,FactoryAdaptWrite write,void *context) {
    if(!idle||!read||!write||!factory_adaptation_valid(a)) return 0;
    FactoryAdaptation old;uint32_t generation=0;
    const uint8_t *r0=read(context,0),*r1=read(context,1);
    int slot=factory_adaptation_load(r0,r1,&old,&generation);
    if(slot<0) {
        /* Ambiguous valid records must not be erased. */
        uint32_t g;FactoryAdaptation check;
        if(factory_adaptation_decode(r0,&check,&g)||factory_adaptation_decode(r1,&check,&g)) return 0;
    } else {
        uint8_t before[34],after[34];pack(before,&old);pack(after,a);
        if(equal(before,after,34)) return 2;
    }
    unsigned target=slot==0?1u:0u;
    uint8_t record[FACTORY_ADAPT_RECORD_BYTES];
    if(!factory_adaptation_encode(record,a,generation+1)||!write(context,target,record,sizeof record)) return 0;
    const uint8_t *got=read(context,target);
    if(!got||!equal(record,got,sizeof record)) return 0;
    return 1;
}
