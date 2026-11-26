#include "factory_core.h"
#include "donor_calibration.h"

/* 0x012F9C. Descending search retains rightmost repeated X. */
uint16_t factory_interp1(uint16_t q, const uint8_t *t) {
    unsigned n=t[0], i=n-1;
    const uint8_t *x=t+1, *y=x+n;
    if ((uint32_t)q >= ((uint32_t)x[i]<<8)) return (uint16_t)(y[i]<<8);
    if ((uint32_t)q < ((uint32_t)x[0]<<8)) return (uint16_t)(y[0]<<8);
    while ((uint32_t)q < ((uint32_t)x[--i]<<8)) {}
    return (uint16_t)(((((uint32_t)x[i+1]<<8)-q)*y[i]
        + (q-((uint32_t)x[i]<<8))*y[i+1])/(x[i+1]-x[i]));
}

static unsigned lower(const uint8_t *x, unsigned n, unsigned stride, uint16_t q) {
    unsigned i=n-1;
    if (q >= ((uint32_t)x[i*stride]<<8)) return i;
    if (q < ((uint32_t)x[0]<<8)) return 0;
    while (q < ((uint32_t)x[--i*stride]<<8)) {}
    return i;
}
static uint32_t row_value(const uint8_t *x, const uint8_t *z, unsigned n,
                          unsigned i, uint16_t q) {
    if (q < ((uint32_t)x[0]<<8) || i==n-1) return (uint32_t)z[i]<<8;
    return ((((uint32_t)x[i+1]<<8)-q)*z[i]
           + (q-((uint32_t)x[i]<<8))*z[i+1])/(x[i+1]-x[i]);
}
/* 0x01321C. X divisions are rounded down BEFORE the Y interpolation. */
uint16_t factory_interp2(uint16_t qx, uint16_t qy, const uint8_t *t) {
    unsigned nx=t[0], ny=t[1], stride=nx+1;
    const uint8_t *x=t+2, *rows=x+nx;
    unsigned i=lower(x,nx,1,qx), j=lower(rows,ny,stride,qy);
    const uint8_t *r=rows+j*stride;
    uint32_t a=row_value(x,r+1,nx,i,qx);
    if (qy < ((uint32_t)rows[0]<<8) || j==ny-1) return (uint16_t)a;
    uint32_t b=row_value(x,r+stride+1,nx,i,qx);
    return (uint16_t)(((((uint32_t)r[stride]<<8)-qy)*a
        + (qy-((uint32_t)r[0]<<8))*b)/((uint32_t)(r[stride]-r[0])<<8));
}

/* 0x012F38. */
uint16_t factory_div_u32_u16(uint32_t n, uint16_t d) {
    uint32_t q=d ? n/d : (n ? 65535u : 0u);
    return (uint16_t)(q>65535u ? 65535u : q);
}
/* 0x027E4E and comparison thresholds from 0x027E9E. */
int16_t factory_atf(uint16_t a) {
    uint16_t q=(uint16_t)(a<2304 ? 0 : a-2304);
    return (int16_t)(((uint32_t)factory_interp1(q,cal_0036E4)*410u>>16)-64);
}
uint8_t factory_atf_status(uint16_t a) { return a<1863 ? 2 : a>64421 ? 1 : 0; }
/* 0x0550E0. Timer period units are not yet mapped to RB VSS input. */
uint16_t factory_period_raw(uint16_t p) {
    uint16_t v=factory_div_u32_u16(0x0217FAB3u,p);
    return v>32767 ? 32767 : v;
}
/* Tail of 0x054F3A. Fault/filter logic preceding this tail is not included. */
uint8_t factory_speed_code(uint16_t raw, uint8_t *alternate) {
    uint32_t a=((uint32_t)raw*2636u)>>18, b=raw>>6;
    if (a>254) a=254;
    if (alternate) *alternate=(uint8_t)a;
    if (a<9) b=0;
    return (uint8_t)(b>254 ? 254 : b);
}
/* Conversion tail of 0x054C00. Raw selection is in factory_inputs.c;
 * its GW4G15 physical input scaling remains a platform integration task. */
uint16_t factory_load_code(uint16_t source) {
    uint16_t q=factory_div_u32_u16((uint32_t)source*25600u,11010);
    return q>25600 ? 25600 : q;
}
/* 0x056040 computes only three consecutive thresholds, starting at index. */
void factory_lookup_thresholds(FactoryRequestState *s) {
    if (s->index_4854>3) return;
    const uint8_t *bank=(s->flags_4846 & 0x20) ? shift_bank_000FEC : shift_bank_001078;
    for (unsigned j=s->index_4854;j<(unsigned)s->index_4854+3;j++)
        s->thresholds_4541[j]=(uint8_t)(factory_interp1(s->load_7202,bank+23*j)>>8);
}
static int valid(const FactoryRequestState *s) {
    return s->index_4854<=3 && s->override_4862<override_limits[2];
}
/* 0x056502, with bounded table search for the valid state domain. */
static void override_thresholds(FactoryRequestState *s) {
    unsigned r=s->override_4862;
    if ((s->flags_4845 & 6) || (s->flags_4844 & 2) || s->speed_4549<override_min_speed)
        goto clear_both;
    if (!r && (s->flags_4844 & 8) && (s->flags_7252 & 32)) {
        s->flags_4839|=2;
        goto clear_timer;
    }
    if (!(s->flags_4839 & 2)) goto clear_timer;
    if (!r && (((s->flags_4844>>3) ^ (s->flags_7252>>5)) & 1)) goto clear_timer;
    if (!(s->flags_p1172 & 1)) s->counter_4771=0;
    s->flags_p1172|=1;
    unsigned i=0;
    while (r>=override_limits[i]) i++;
    if (s->index_4854 || s->counter_4771>=override_counts[i]) goto clear_both;
    goto apply;
clear_both:
    s->flags_4839 &= (uint8_t)~2u;
clear_timer:
    s->flags_p1172 &= (uint8_t)~1u;
apply:
    if (s->flags_4839 & 2) {
        for (unsigned j=s->index_4854;j<(unsigned)s->index_4854+3;j++) {
            if (!r) s->thresholds_4541[j]=override_thresholds_rom[j];
            if ((s->flags_p1172 & 1) && j<3) s->thresholds_4541[j]=255;
        }
    }
}
/* Entire 0x055F48 including both calls. No physical shift actuation. */
int factory_request_normal(FactoryRequestState *s) {
    if (!valid(s)) return 0;
    factory_lookup_thresholds(s);
    override_thresholds(s);
    if (s->flags_4845 & 6) return 1;
    unsigned original=s->index_4854;
    uint8_t target=(uint8_t)original;
    for (unsigned i=0;i<3;i++) {
        unsigned k=original+i;
        if (k<3) { if (s->speed_4549>=s->thresholds_4541[k]) target++; }
        else if (s->speed_4549<s->thresholds_4541[5-i]) target--;
    }
    s->index_4854=target;
    return 1;
}
/* 0x055FB0. */
int factory_request_special1(FactoryRequestState *s) {
    if (s->index_4854>3) return 0;
    if ((s->flags_4845 & 4) || !(s->flags_4845 & 2)) return 1;
    uint8_t t=s->index_4854;
    factory_lookup_thresholds(s);
    if (t==2 || t==3) {
        if (t==3) t--;
        if (s->speed_4549<special_limits[2]) t=1;
    }
    if (t==1 && s->speed_4549<s->thresholds_4541[3]) t--;
    else if (!t && s->speed_4549>=s->thresholds_4541[0]) t++;
    s->index_4854=t;
    return 1;
}
/* 0x05600A. */
int factory_request_special2(FactoryRequestState *s) {
    if (s->index_4854>3) return 0;
    if (!(s->flags_4845 & 4)) return 1;
    uint8_t t=s->index_4854;
    if (t) {
        if (t==3) t--;
        if (s->speed_4549<special_limits[1]) t=1;
        if (s->speed_4549<special_limits[0]) t=0;
    }
    s->index_4854=t;
    return 1;
}
int factory_request_stage(FactoryRequestState *s) {
    if (!valid(s)) return 0;
    factory_request_normal(s);
    factory_request_special1(s);
    factory_request_special2(s);
    return 1;
}
uint16_t factory_slt_characteristic(uint16_t q) { return factory_interp1(q,cal_000FBC); }
int16_t factory_slt_select(int16_t base, int16_t correction, int16_t limit,
    int16_t override_value, uint8_t f9748, uint8_t f4830, uint8_t fp1156) {
    int32_t v=base;
    if ((f9748 & 1) && (f4830 & 64)) {
        uint32_t bits=(uint32_t)(v+correction)&65535u;
        v=bits>=32768u ? (int32_t)bits-65536 : (int32_t)bits;
    }
    if (v<0) v=0;
    if (v>limit) v=limit;
    if (fp1156 & 1) v=override_value;
    return (int16_t)v;
}
uint16_t factory_slu_characteristic(uint16_t q) { return factory_interp1(q,cal_000FD4); }
/* 0x01EF68 positive command domain, excluding hardware call 0x01AC78. */
uint16_t factory_driver_count(uint16_t q) {
    return (uint16_t)(400u+(((uint32_t)q*3600u)>>8)/100u);
}
uint8_t factory_s1_s2_requests(uint8_t i) {
    if (i>3) return 255;
    return (uint8_t)((i<=1 ? 1 : 0) | ((i==0 || i==3) ? 2 : 0));
}
uint8_t factory_bank_flags(uint8_t old, uint8_t a, uint8_t b, uint8_t c,
    uint8_t d, uint8_t e, uint8_t f, uint8_t g) {
    uint8_t out=(uint8_t)(old & (uint8_t)~0x70u);
    if ((a & 16) || (b & 16) || (c & 4)) out|=16;
    if (d & 2) out|=64;
    if (!e || (out & 64) || (f & 16) || (g & 16) || (a & 16)) out|=32;
    return out;
}
#include "factory_core.h"

void factory_pressure_snapshot(FactoryPressureSnapshot *s)
{
    s->selected_p1158 = s->source_7148;
    if (s->flags_4829 & 1) s->selected_p1158 = s->source_7146;
    if (s->flags_4830 & 128) s->selected_p1158 = s->source_7144;
    if (s->flags_9748 & 1) s->selected_p1158 = s->source_7142;
    s->flags_p1156 = (s->flags_p1156 & (uint8_t)~1) | ((s->flags_4841 >> 2) & 1);
    if (!(s->flags_9746 & 1)) s->index_4856 = 255;
}

