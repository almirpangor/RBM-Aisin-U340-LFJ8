#include "factory_phase_modes.h"
#include "factory_core.h"
#include "donor_calibration.h"
static uint16_t u16(const uint8_t *p) { return p[0]|((uint16_t)p[1]<<8); }
static int32_t s16(uint16_t v) { return v<32768 ? v : (int32_t)v-65536; }
static int32_t s32(uint32_t v) { return v<=0x7fffffffu ? (int32_t)v : -1-(int32_t)~v; }
static uint16_t twice(uint16_t v) { v=(uint16_t)(2u*v);return v<32640 ? v : 32640; }
static uint8_t satinc(uint8_t v) { return v==255 ? 255 : (uint8_t)(v+1); }
static uint8_t cap255(unsigned v) { return v>255 ? 255 : (uint8_t)v; }
int16_t factory_div_s32_s16(int32_t n,int16_t d)
{
    if (!n) return 0;
    if (!d) return n<0 ? -32768 : 32767;
    if (n==(-2147483647-1) && d==-1) return 32767;
    int32_t q=n/d;return (int16_t)(q>32767 ? 32767 : q< -32768 ? -32768 : q);
}
static FactoryQueuedPhase getq(const FactoryPhaseModes *s,unsigned i)
{
    if(i) return s->queued[i-1];
    FactoryQueuedPhase q={s->phase.flags_9748,s->phase.input_7100,s->phase.input_7094,
        s->phase.input_7088,s->phase.index_4514,s->phase.index_4519,s->phase.count_4749,s->count_4696};
    return q;
}
static void putq(FactoryPhaseModes *s,unsigned i,FactoryQueuedPhase q)
{
    if(i) {s->queued[i-1]=q;return;}
    s->phase.flags_9748=q.flags;s->phase.input_7100=q.sample_7100;s->phase.input_7094=q.sample_7094;
    s->phase.input_7088=q.ratio_7088;s->phase.index_4514=q.index_4514;
    s->phase.index_4519=q.index_4519;s->phase.count_4749=q.count_4749;s->count_4696=q.count_4696;
}
static int enqueue(FactoryPhaseModes *s)
{
    unsigned target=s->phase.index_4852,previous=s->index_4851,count=s->count_p1440;
    if(target>3 || previous>3 || count>3) return 0;
    uint16_t turbine=twice((uint16_t)s->phase.input_7208);
    if(!(s->flags_7252&8)) while(previous!=target) {
        FactoryQueuedPhase old=getq(s,count ? count-1 : 0),q={0};
        uint16_t sample=twice((uint16_t)s->phase.input_7204);
        q.flags=0x10001;
        if(previous<target) {
            q.flags|=2;s->counts_4511[previous]=satinc(s->counts_4511[previous]);
            if(count<3)++count;
            if(!(old.flags&2))count=1;
            q.flags|=previous<<2;++previous;
        } else {
            if((s->phase.flags_4845&4) || ((s->phase.flags_4845&2)&&target>=1) ||
                ((s->phase.flags_4845&1)&&target==2)) q.flags|=32;
            if(previous==3 && target==1) {previous=1;q.flags|=16;}
            else if(previous==2 && target==0) {previous=0;q.flags|=12;}
            else {--previous;q.flags|=(previous&7)<<2;}
            unsigned oldmode=(old.flags>>2)&7;
            if(!(old.flags&2)) {
                if(oldmode==1 && !(old.flags&0x2000)) {
                    if(!count)return 0;
                    old.flags=(old.flags&~0x1cu)|12;putq(s,count-1,old);break;
                }
                if(oldmode==2 && (s->phase.flags_4842&8)) {
                    if(!count)return 0;
                    old.flags|=0x100;putq(s,count-1,old);
                    if(count<3)++count;
                    q.flags|=0x200;
                } else count=1;
            } else {
                count=1;
                if(oldmode==2 && ((q.flags>>2)&7)==4) q.flags|=0x80000;
            }
        }
        unsigned bank=(q.flags>>2)&7;if(bank>=3)bank-=3;
        if(bank>2 || !count || count>3)return 0;
        unsigned speedbin=0,loadbin=0;
        while(speedbin<6 && (sample>>7)>=u16(pressure_0015FC+12*bank+2*speedbin))++speedbin;
        while(loadbin<5 && s->phase.speed_4549>=u16(mode_001620+10*bank+2*loadbin))++loadbin;
        if(speedbin>=6 || loadbin>=5)return 0;
        q.sample_7100=sample;q.sample_7094=turbine;q.index_4514=(uint8_t)speedbin;q.index_4519=(uint8_t)loadbin;
        q.ratio_7088=factory_div_s32_s16((int32_t)s->phase.input_7204*4096,s->phase.input_7208);
        putq(s,count-1,q);
    }
    FactoryQueuedPhase empty={0};empty.count_4749=255;empty.count_4696=255;
    for(unsigned i=count;i<3;++i)putq(s,i,empty);
    s->count_p1440=(uint8_t)count;return 1;
}
static int pop(FactoryPhaseModes *s)
{
    putq(s,0,getq(s,1));putq(s,1,getq(s,2));
    FactoryQueuedPhase empty={0};empty.count_4749=255;empty.count_4696=255;
    putq(s,2,empty);if(s->count_p1440)--s->count_p1440;return 1;
}
static int deadline(FactoryPhaseModes *s)
{
    uint32_t flags=s->phase.flags_9748;
    unsigned mode=(flags>>2)&7,positive=(flags>>1)&1,bank=mode;
    if(mode>4 || (positive && mode>2) || s->phase.index_4514>5 || s->phase.index_4519>4)return 0;
    if(positive)++bank;else if(bank>=3)bank-=3;
    int32_t reference=bank ? s->phase.inputs_9728[bank-1] : s->input_9732;
    int32_t x=s->phase.input_7204,y=x,a=reference,b=reference;
    unsigned limit;
    if(positive) {
        limit=mode_0015D8[mode*6+s->phase.index_4514];
        if(mode==2) {y=-y;b=s32(0u-(uint32_t)b);}
        if(!(s->phase.flags_4842&2))mode+=3;
    } else {
        limit=mode_0015EC[bank*5+s->phase.index_4519];
        x=-x;a=s32(0u-(uint32_t)a);mode+=6;
        if(!(s->phase.flags_4842&8))mode+=5;
    }
    if(!(s->phase.flags_4846&16)) {
        s->count_p1446=satinc(s->count_p1446);
        unsigned original=(flags>>2)&7;
        int32_t threshold=s16(u16(mode_001744+(original==2||original==4 ? 0x2a : 0x28)));
        int reset=x>=s32((uint32_t)a+(uint32_t)threshold);
        if(original==2 || original==4) reset|=y>=s32((uint32_t)b+(uint32_t)threshold);
        if(reset)s->count_p1446=0;
        if(s->count_p1446>=mode_001744[0x70+mode]) {
            flags|=0x2000;s->count_p1446=0;s->count_4693=0;
        }
    }
    if(s->count_4696>=limit) {flags|=0x3000;s->count_p1446=0;s->count_4693=0;}
    s->phase.flags_9748=flags;s->output_4508=(uint8_t)(limit>>1);return 1;
}
static int delay32(FactoryPhaseModes *s)
{
    FactoryPhaseCycle *p=&s->phase;
    if(s->index_4851==3 && p->index_4852==2) {
        s->count_4746=0;p->flags_4831|=64;p->flags_p1449&=(uint8_t)~4;
        if(s->count_4744<4)p->flags_p1449|=4;
        for(unsigned i=0;i<6;++i)s->saved_p1464[i]=255;
    }
    if(p->flags_4831&64) {
        unsigned bank=0,row=0;
        if(s->index_4854>=1) {bank=row=(p->flags_p1449&4) ? 4 : 2;if(p->flags_4845&6)row=6;}
        if(!(p->flags_4842&8)) {++bank;++row;}
        for(unsigned i=0;i<6;++i) if(s->saved_p1464[i]==255) {
            int latch=s->count_4746>=mode_001744[0x59];
            if(!latch && s->count_4746>=mode_001744[0x58] && !(p->flags_4846&16)) {
                uint16_t delta=factory_interp1((uint16_t)p->speed_4549<<7,mode_001B38+11*i)>>2;
                latch=p->input_7204>=s32((uint32_t)p->inputs_9728[1]-delta);
            }
            if(latch)s->saved_p1464[i]=s->count_4746;
        }
        if(s->count_4746>=cap255(s->saved_p1464[bank]+mode_001744[0x20+row]))p->flags_4831&=(uint8_t)~64;
    }
    if(p->flags_9748&1)s->count_4744=0;
    return 1;
}
static int delay31(FactoryPhaseModes *s)
{
    FactoryPhaseCycle *p=&s->phase;
    if(s->index_4851==3 && p->index_4852==1) {
        p->flags_4831|=128;s->count_4745=0;s->saved_p1470[0]=s->saved_p1470[1]=255;
    }
    if(p->flags_4831&128) {
        unsigned bank=!(p->flags_4842&8);
        for(unsigned i=0;i<2;++i) if(s->saved_p1470[i]==255) {
            int latch=s->count_4745>=mode_001744[0x5b];
            if(!latch && s->count_4745>=mode_001744[0x5a] && !(p->flags_4846&16)) {
                uint16_t delta=factory_interp1((uint16_t)p->speed_4549<<7,mode_00181C+11*i)>>2;
                latch=p->input_7204>=s32((uint32_t)p->inputs_9728[0]-delta);
            }
            if(latch)s->saved_p1470[i]=s->count_4745;
        }
        if(s->count_4745>=cap255(s->saved_p1470[bank]+mode_001744[0x50+bank]))p->flags_4831&=(uint8_t)~128;
    }
    return 1;
}
static int trim(FactoryPhaseModes *s)
{
    int32_t step=s16(u16(mode_001744+0x52));
    int32_t v=s16(s->phase.input_7224)+((s->flags_4832&128) ? step : -step);
    v=s16((uint16_t)v);s->phase.input_7224=(uint16_t)(v<0 ? 0 : v>5120 ? 5120 : v);return 1;
}
static int modes(FactoryPhaseModes *s)
{
    if(!enqueue(s) || !delay31(s) || !delay32(s))return 0;
    FactoryPhaseCycle *p=&s->phase;
    if(p->flags_9748&1) {
        p->flags_4831&=(uint8_t)~32;
        if(((p->flags_9748&2) && !(p->flags_4842&2)) ||
            (!(p->flags_9748&2) && !(p->flags_4842&8))) {p->flags_9748|=0x20000;p->flags_4831|=32;}
        if((p->flags_9748&0x100) && (p->flags_4842&8)) {if(!(s->flags_4833&128))pop(s);}
        else if(!(p->flags_9748&0x2000)) {if(!deadline(s))return 0;}
        unsigned mode=(p->flags_9748>>2)&7,row=mode,limit1=255,limit2=255;
        if(mode>4 || ((p->flags_9748&2)&&mode>2))return 0;
        if(p->flags_9748&2) {
            limit1=mode_001744[mode];
            if(mode==2) {limit2=mode_001744[4];if(s->index_4854<2)limit1=mode_001744[3];}
            if(mode==0 && (p->flags_4845&6))row=3;
        } else row=mode==1 && (p->flags_4845&6) ? 9 : mode+4;
        unsigned special=(p->flags_4831>>5)&1;
        if(special)row+=10;
        if(p->flags_9748&0x1000)row=(p->flags_9748&2) && p->input_7184<10240 ? mode+20 : 22;
        if(!(p->flags_9735&32))s->limit_p1441=mode_001744[8+row];
        if(p->flags_9748&0x2000) {
            if(p->flags_4842&2) {
                if(!(p->flags_9748&0x8000) && mode==2 && (p->flags_9748&2)) {
                    p->flags_9748|=0x8000;s->count_4691=0;
                }
            } else p->flags_9748&=~0x8000u;
            if(s->count_4693>=4) {
                p->flags_9748&=~0x10000u;
                if(special)p->flags_9748&=~0x4000u;
                else if(!(p->flags_9748&0x4000) && (p->flags_9748&2) &&
                    ((s->flags_4840&2) || ((s->flags_4840&4)&&p->index_4852==3))) {
                    p->flags_9748|=0x4000;s->count_4692=0;
                }
                if(s->count_4693>=s->limit_p1441 ||
                    ((p->flags_9748&0x4000)&&s->count_4692>=limit1) ||
                    ((p->flags_9748&0x8000)&&s->count_4691>=limit2) || s->count_p1440>1) {
                    if(mode==2 && (p->flags_9748&2))trim(s);
                    pop(s);
                }
            }
        }
    }
    return factory_phase_cycle(p);
}
#define WRAP(name,impl) int name(FactoryPhaseModes *s) { if(!s)return 0; FactoryPhaseModes t=*s; if(!impl(&t))return 0; *s=t;return 1; }
WRAP(factory_phase_enqueue,enqueue)
WRAP(factory_phase_pop,pop)
WRAP(factory_phase_deadline,deadline)
WRAP(factory_phase_delay32,delay32)
WRAP(factory_phase_delay31,delay31)
WRAP(factory_phase_trim,trim)
WRAP(factory_phase_modes_step,modes)
