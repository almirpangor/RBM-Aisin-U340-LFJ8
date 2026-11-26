#include "factory_pressure.h"
#include "factory_core.h"
#include "donor_calibration.h"

/* Explicit arithmetic shift and sign extension, including negative test inputs. */
static int32_t sar(int32_t x, uint8_t n)
{ return x >= 0 ? x / (1 << n) : -1 - ((-1-x) / (1 << n)); }
static int32_t signed16(int32_t x)
{ uint32_t y=(uint32_t)x & 65535u; return y<32768u ? (int32_t)y : (int32_t)y-65536; }
static int32_t clamp(int32_t x)
{ return x<0 ? 0 : x>25600 ? 25600 : x; }
static uint16_t word(const uint8_t *p)
{ return (uint16_t)p[0] | ((uint16_t)p[1]<<8); }
static int32_t signed32(uint32_t v)
{ return v<=0x7fffffffu ? (int32_t)v : -1-(int32_t)(~v); }

int factory_phase_cycle(FactoryPhaseCycle *s)
{
    if (!s) return 0;
    FactoryPhaseDemand demand={
        .flags_9748=s->flags_9748,.input_9724=s->inputs_9728[1],
        .input_7100=s->input_7100,.input_7094=s->input_7094,
        .input_7152=s->input_7152,.input_7184=s->input_7184,
        .memory_p1452=s->memory_p1452,.input_7154=s->input_7154,
        .input_7224=s->input_7224,.output_p1462=s->pressure_p1462,
        .input_7106=s->input_7106,.input_7204=s->input_7204,.input_7208=s->input_7208,
        .index_4514=s->index_4514,.index_4545=s->index_4545,.index_4546=s->index_4546,
        .flags_4838=s->flags_4838,.flags_4843=s->flags_4843,.flags_4846=s->flags_4846,
        .flags_5139=s->flags_5139,.flags_4842=s->flags_4842,.flags_4844=s->flags_4844,
        .index_4519=s->index_4519,.input_7200=s->input_7200
    };
    for (unsigned i=0;i<18;++i) demand.learned_4579[i]=s->learned_4579[i];
    for (unsigned i=0;i<5;++i) demand.learned_4554[i]=s->learned_4554[i];
    if (!factory_phase_demand(&demand)) return 0;
    FactoryPhasePressure phase={
        .flags_9748=demand.flags_9748,
        .inputs_9728={s->inputs_9728[0],s->inputs_9728[1],s->inputs_9728[2]},
        .input_7244=s->input_7244,.input_7184=s->input_7184,.input_7100=s->input_7100,
        .input_7200=s->input_7200,.input_7154=s->input_7154,.input_7204=s->input_7204,
        .pressure_p1462=demand.output_p1462,.subtract_p1458=s->subtract_p1458,
        .ramp_p1456=s->ramp_p1456,.subtract_p1454=s->subtract_p1454,
        .hold_p1460=s->hold_p1460,.saved_p1450=s->saved_p1450,.output_7142=s->output_7142,
        .flags_9736=s->flags_9736,.flags_9735=s->flags_9735,.flags_4846=s->flags_4846,
        .flags_4842=s->flags_4842,.flags_4831=s->flags_4831,.flags_4845=s->flags_4845,
        .flags_4844=s->flags_4844,.flags_p1449=s->flags_p1449,
        .selector_p1444=s->selector_p1444,.count_p1445=s->count_p1445,
        .index_4514=s->index_4514,.index_4852=s->index_4852,.speed_4549=s->speed_4549
    };
    if (!factory_pressure_window(&phase) || !factory_pressure_ramp(&phase)) return 0;
    FactoryPressureFeedback feedback={
        .flags_9748=phase.flags_9748,.input_7088=s->input_7088,.input_7208=s->input_7208,
        .input_7204=s->input_7204,.subtract_p1454=s->subtract_p1454,
        .flags_9736=s->flags_9736,.flags_9735=s->flags_9735,.flags_4842=s->flags_4842,
        .count_p1448=s->count_p1448,.count_p1447=s->count_p1447,.count_4749=s->count_4749
    };
    if (!factory_pressure_feedback(&feedback)) return 0;
    phase.flags_9748=feedback.flags_9748;phase.subtract_p1454=feedback.subtract_p1454;
    factory_phase_pressure(&phase);
    s->flags_9748=phase.flags_9748;
    s->pressure_p1462=demand.output_p1462;s->memory_p1452=demand.memory_p1452;
    s->subtract_p1458=phase.subtract_p1458;s->ramp_p1456=phase.ramp_p1456;
    s->subtract_p1454=phase.subtract_p1454;s->hold_p1460=phase.hold_p1460;
    s->saved_p1450=phase.saved_p1450;s->output_7142=phase.output_7142;
    s->flags_p1449=phase.flags_p1449;s->selector_p1444=phase.selector_p1444;
    s->count_p1445=phase.count_p1445;
    s->count_p1448=feedback.count_p1448;s->count_p1447=feedback.count_p1447;
    return 1;
}

int factory_pressure_feedback(FactoryPressureFeedback *s)
{
    if (!s) return 0;
    unsigned mode=(s->flags_9748>>2)&7;
    int active=(s->flags_9748 & 2) && !(s->flags_4842 & 2);
    if (active && mode>2) return 0;
    uint32_t correction=s->subtract_p1454;
    if ((s->flags_9736 & 0x1e)!=(s->flags_9748 & 0x1e)) {
        correction=0;
        s->count_p1448=0;s->count_p1447=0;
    }
    if (active) {
        int32_t reference=sar((int32_t)s->input_7208*s->input_7088,12);
        if (s->input_7204>=reference+signed16(word(pressure_001774+2*mode))) {
            if (s->count_p1448<255) ++s->count_p1448;
        } else s->count_p1448=0;
        if (s->input_7204<reference-signed16(word(pressure_00177C+2*mode))) {
            if (s->count_p1447<255) ++s->count_p1447;
        } else s->count_p1447=0;
        if (s->count_4749>=pressure_0017A8[mode] &&
            s->count_p1448>=pressure_0017A8[mode+3]) s->flags_9748|=0x0400;
        if (s->count_p1447>=pressure_0017A8[mode+6]) {
            s->flags_9748&=~0x0400u;s->flags_9748|=0x0800;
        }
        if (s->flags_9748 & 0x0400) {
            correction+=word(pressure_00178C+2*mode);
            if (!(s->flags_9735 & 4)) correction=word(pressure_001784+2*mode);
        }
    } else { correction=0;s->flags_9748&=~0x0c00u; }
    s->subtract_p1454=(uint16_t)(correction>=25600 ? 25600 : correction);
    return 1;
}

int factory_phase_demand(FactoryPhaseDemand *s)
{
    if (!s) return 0;
    uint32_t flags=s->flags_9748;
    unsigned mode=(flags>>2)&7;
    if (mode>4 || ((flags & 2) && mode>2) || s->index_4514>5 ||
        s->index_4545>6 || s->index_4546>6 || s->index_4519>4) return 0;
    uint16_t axis=(uint16_t)(s->input_7100*2u);
    uint16_t speed=(uint16_t)(s->input_7094*2u);
    uint16_t load=s->input_7152, peak=s->memory_p1452;
    unsigned load_index=s->index_4545, speed_index=s->index_4514;
    if (flags & 0x2000) {
        axis=s->input_7204>=16384 ? 65535 : (uint16_t)((int32_t)s->input_7204*4);
        speed=s->input_7208>=16384 ? 65535 : (uint16_t)((int32_t)s->input_7208*4);
        load=s->input_7154;load_index=s->index_4546;
        if (flags & 2) {
            speed_index=0;
            while (speed_index<6 && (axis>>8)>=word(pressure_0015FC+12*mode+2*speed_index))
                ++speed_index;
            if (speed_index>=6) return 0;
        }
    }
    unsigned temp_bank=load_index>=4, speed_bank=(speed>>8)>=88;
    if (s->flags_4838 & 2) peak=0;
    if (!(s->flags_4843 & 4) && s->input_7106>=(int32_t)(peak>>1))
        peak=(uint16_t)((int32_t)s->input_7106*2);
    int32_t pressure=0;
    if (flags & 2) {
        pressure=(factory_interp2(load,axis,pressure_001890+57*mode)>>1)+
            (factory_interp1(s->input_7184,pressure_00193C+15*(temp_bank+2*mode))>>1)-7680;
        if (!(flags & 0x20000)) {
            pressure=clamp(pressure+64*(int32_t)s->learned_4579[6*mode+s->index_4514]);
            if (mode==2) {
                pressure-=s->input_7224;
                int32_t threshold=signed32((uint32_t)s->input_9724+
                    (uint32_t)signed16(word(pressure_001770+2)));
                if ((flags & 0x40000) || s->input_7204>=threshold) {
                    flags|=0x40000;
                    pressure-=factory_interp1(peak,pressure_0017A0)>>1;
                }
            }
        }
        if ((s->flags_4846 & 48) || (s->flags_5139 & 2))
            pressure-=(int32_t)pressure_001998[(mode*7+load_index)*6+speed_index]<<7;
        if (!(s->flags_4842 & 2))
            pressure=mode<2 ? (int32_t)pressure_001770[mode]<<7 :
                factory_interp1(speed,pressure_001834)>>1;
    } else {
        unsigned row=mode;
        if (mode==0) pressure=factory_interp1(load,pressure_001840)>>1;
        else if (mode<=3) {
            if (mode==1 && (flags & 32)) --row;
            pressure=factory_interp2(load,speed,pressure_001A18+49*row)>>1;
        }
        row=mode==3 ? 0 : mode==4 ? 3 : mode;
        if (row<3)
            pressure+=(factory_interp1(s->input_7184,pressure_001ADC+15*(speed_bank+2*row))>>1)-7680;
        if (flags & 0x0200) pressure-=(int32_t)pressure_001798[row]<<7;
        if (mode==2) pressure=clamp(pressure+64*(int32_t)s->learned_4554[s->index_4519]);
        int32_t alternate=factory_interp1(speed,pressure_001B7C+9*row)>>1;
        if (row>=1) {
            --row;
            if (!(s->flags_4844 & 32))
                alternate+=factory_interp2(load,speed,pressure_001BA0+36*row)>>1;
            alternate+=(factory_interp1(s->input_7184,pressure_001C0C+15*row)>>1)-7680;
        }
        if (flags & 0x20000) {
            pressure=(int32_t)pressure_001798[2]<<7;
            if (mode==2 || mode==4)
                pressure=alternate-(factory_interp1(s->input_7200,pressure_0017EC+7*((mode>>1)-1))>>1);
        }
        if (!(s->flags_4842 & 8) || (mode==4 && !(flags & 0x20000))) {
            pressure=(int32_t)pressure_001798[2]<<7;
            if (flags & 32) {
                pressure=alternate;
                if (flags & 0x80000) pressure-=factory_interp1(speed,pressure_001850)>>1;
            }
        }
    }
    s->flags_9748=flags;
    s->output_p1462=(uint16_t)clamp(pressure);
    s->memory_p1452=peak;
    return 1;
}

int factory_pressure_window(FactoryPhasePressure *s)
{
    if (!s || s->input_7184==65535 || s->selector_p1444>1) return 0;
    uint8_t row=0;
    while (row<7) {
        uint16_t threshold=(uint16_t)pressure_0017FC[2*row] |
            ((uint16_t)pressure_0017FC[2*row+1]<<8);
        if (s->input_7184<threshold) break;
        ++row;
    }
    if (row>=7) return 0;
    s->flags_9748&=~64u;
    s->subtract_p1458=(uint16_t)pressure_00179B[0]<<7;
    int32_t prior=s->input_7244, demand=s->pressure_p1462;
    if (!(s->flags_9736 & 1) && (s->flags_9748 & 1) &&
        ((prior<demand && demand-prior<s->subtract_p1458) || prior>demand)) {
        s->count_p1445=0;
        s->selector_p1444=(uint8_t)(prior<23040);
    }
    if (s->count_p1445<pressure_00180C[row+7*s->selector_p1444]) {
        s->flags_9748|=64;
        ++s->count_p1445;
    } else s->count_p1445=255;
    return 1;
}

int factory_pressure_ramp(FactoryPhasePressure *s)
{
    if (!s) return 0;
    uint8_t mode=(uint8_t)((s->flags_9748>>2)&7);
    uint8_t positive=(uint8_t)((s->flags_9748>>1)&1);
    if (positive && (mode>2 || s->index_4514>5)) return 0;
    /* An already set bit 7 can still enter the incremental branch when
     * bit 1 is clear. Guard that dynamic lookup before any mutation. */
    if (!(s->flags_9748 & 0x2000) && (s->flags_9748 & 128) &&
        (s->flags_p1449 & 1) && (mode>2 || s->index_4514>5)) return 0;
    uint16_t ceiling=0;
    int32_t threshold=0;
    if (positive) {
        ceiling=(uint16_t)pressure_0017D8[mode*6+s->index_4514]<<7;
        uint32_t bits=(uint32_t)s->inputs_9728[mode]+
            (factory_interp1(s->input_7100,pressure_00185C+17*mode)>>2);
        threshold=bits<=0x7fffffffu ? (int32_t)bits : -1-(int32_t)(~bits);
    }
    if (s->flags_9748 & 0x2000) s->flags_9748&=~128u;
    else if (positive && s->input_7204<threshold && !(s->flags_4846 & 16) &&
        ceiling && !(s->flags_9748 & 128)) {
        s->flags_9748|=128;
        s->ramp_p1456=0;
        s->flags_p1449&=(uint8_t)~1;
    }
    if (s->flags_9748 & 128) {
        if (s->flags_p1449 & 1) {
            s->flags_p1449&=(uint8_t)~1;
            s->ramp_p1456=(uint16_t)(s->ramp_p1456+
                ((uint16_t)pressure_0017C4[mode*6+s->index_4514]<<7));
            if (s->ramp_p1456>ceiling) s->ramp_p1456=ceiling;
        } else s->flags_p1449|=1;
    }
    return 1;
}

void factory_phase_pressure(FactoryPhasePressure *s)
{
    uint32_t flags=s->flags_9748;
    int32_t pressure=(flags & 1) ? s->pressure_p1462 : 0;
    if (flags & 64) pressure-=s->subtract_p1458;
    if (flags & 128) pressure+=s->ramp_p1456;
    if (flags & 0x0c00) pressure-=s->subtract_p1454;
    pressure=clamp(pressure);
    if (flags & 0x2000) {
        if (!(s->flags_9735 & 32)) {
            s->hold_p1460=s->output_7142;
            s->saved_p1450=s->input_7200;
            s->flags_p1449&=(uint8_t)~2;
        }
        uint8_t phase=(uint8_t)((flags>>1)&1);
        if (signed16(s->saved_p1450)-signed16(s->input_7200)>=1280 ||
            (phase && (s->flags_4842 & 4) && !(s->flags_4842 & 2)) ||
            (!phase && (s->flags_4842 & 16) && !(s->flags_4842 & 8)))
            s->flags_p1449|=2;
        if (pressure>=s->hold_p1460 && !(s->flags_p1449 & 2))
            pressure=s->hold_p1460;
        if (s->index_4852<2 && (s->flags_4831 & 32) &&
            ((s->flags_4845 & 4) || ((s->flags_4845 & 2) && s->index_4852==1))) {
            uint8_t map=s->index_4852, bank=0;
            uint16_t speed=(uint16_t)s->speed_4549<<8;
            if (((flags>>2)&7)==4) { map=3; bank=2; }
            pressure=factory_interp1(speed,pressure_001B7C+9*map)>>1;
            if (s->index_4852==1) {
                pressure+=(factory_interp1(s->input_7184,pressure_001C0C+15*bank)>>1)-7680;
                if (!(s->flags_4844 & 32))
                    pressure+=factory_interp2(s->input_7154,speed,pressure_001BA0+36*bank)>>1;
            }
        }
    }
    if ((flags & 0x8000) && pressure>=25600) pressure=25600;
    if (flags & 0x4000) pressure=0;
    s->output_7142=(uint16_t)clamp(pressure);
}

int factory_pressure_limit(FactoryPressureLimit *s)
{
    if (!s) return 0;
    if (!(s->flags_9748 & 1)) { s->limit_7138=25600; return 1; }
    int row=s->row_p1586;
    if (s->index_4852>3 || s->index_4851>3) return 0;
    if (s->index_4852!=s->index_4851)
        row=(int)s->index_4852-1+(s->index_4852<s->index_4851 ? 4 : 0);
    if (row<0 || row>5) return 0;
    if (s->index_4852!=s->index_4851) {
        s->row_p1586=(int16_t)row;
        uint16_t scaled=(uint16_t)((uint32_t)s->input_7204*2);
        s->saved_p1584=scaled<32640 ? scaled : 32640;
    }
    uint32_t limit=factory_interp1(s->input_7154,pressure_00209C+21*row);
    if (row==1) {
        uint16_t alternate=factory_interp1(s->input_7152,pressure_002084);
        if (alternate<limit) limit=alternate;
    }
    if (row==2 || row==5)
        limit+=factory_interp1(s->saved_p1584,pressure_002060+17*(row/4));
    s->limit_7138=(uint16_t)(limit>25600 ? 25600 : limit);
    return 1;
}

void factory_pressure_override(FactoryPressureOverride *s)
{
    s->flags_4829|=1;
    int qualified=!(s->flags_p1588 & 1) &&
        (((s->flags_4846 & 128) && s->index_4852==3) ||
         ((s->flags_4845 & 1) && s->index_4852==2)) &&
        !(s->flags_4841 & 80) && (s->flags_4844 & 8) &&
        s->input_7164>=30720 && s->input_7184>=17920;
    if (!qualified) { s->flags_4829&=(uint8_t)~1; s->count_4742=0; }
    s->output_7146=s->count_4742>=24 ? 25600 : 0;
    if (s->count_4742>=49) s->flags_p1588|=1;
}

void factory_pressure_special(FactoryPressureSpecial *s)
{
    int active_inputs=s->flags_7252 & 6;
    if (!(s->flags_4838 & 2) && s->index_4852==1) {
        if ((!(s->flags_7250 & 4) && (s->flags_7252 & 4)) ||
            (!(s->flags_7250 & 2) && (s->flags_7252 & 2))) {
            s->flags_4830|=128;
            s->count_4743=0;
            s->saved_p1576=s->speed_4549;
        }
        if (s->count_4743>=pressure_002008[0] || !active_inputs)
            s->flags_4830&=127;
    } else s->flags_4830&=127;
    int32_t output=0;
    if (s->flags_4830 & 128) {
        uint16_t speed=(uint16_t)s->saved_p1576<<8;
        output=(factory_interp1(speed,pressure_001B85)>>1)+
            (factory_interp1(s->input_7184,pressure_001C0C)>>1)-7680;
        if (!(s->flags_4844 & 32))
            output+=factory_interp2(s->input_7152,speed,pressure_001BA0)>>1;
        output=clamp(output);
    }
    s->output_7144=(uint16_t)output;
}

void factory_base_pressure(FactoryBasePressure *s)
{
    uint8_t bank = s->index_4848 >= 1 &&
        (((s->flags_4835 & 64) && !(s->flags_4834 & 1)) || (s->flags_4829 & 24));
    int32_t v=(int32_t)factory_interp1(s->input_7154,pressure_00200C+7*bank)-12544;
    if (v<0) v=0;
    uint32_t scaled=(uint32_t)factory_div_u32_u16((uint32_t)v<<8,340)*2u;
    if (scaled>65535u) scaled=65535u;
    int32_t ceiling=factory_interp1((uint16_t)scaled,pressure_002044)>>1;
    uint8_t curve=1;
    if (s->index_4852>1 && s->index_4848>1 &&
        s->input_7204<sar((int32_t)s->input_7208*11469,13) &&
        ((s->flags_4846 & 128) || (s->flags_4845 & 1)) &&
        s->speed_4548>=10 && !(s->flags_4846 & 16)) curve=0;
    int32_t demand=s->input_7198, previous=s->memory_p1580;
    if (!(s->flags_7252 & 1) && s->speed_4548<10 && s->input_7204<1280 &&
        previous>=demand+1792)
        demand=signed16(previous-sar(previous-demand,5));
    demand=clamp(demand);
    s->memory_p1580=(int16_t)demand;
    int32_t normal=factory_interp1((uint16_t)demand,pressure_00201C+19*curve)>>1;
    int32_t output=factory_interp1(25600,pressure_00201C+19)>>1;
    if (!(s->flags_4846 & 64) && !(s->flags_5299 & 2)) {
        output=normal;
        if (!(s->flags_4844 & 128) && output>ceiling) output=ceiling;
    }
    s->output_7148=(int16_t)clamp(output);
}
