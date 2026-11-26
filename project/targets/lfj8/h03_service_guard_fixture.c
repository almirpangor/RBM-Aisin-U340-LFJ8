#include "lfj8_h03_service_guard.h"
#include <assert.h>
#include <stdio.h>

void __init(void) {}
void __fini(void) {}

int main(void)
{
    const Lfj8H03ServicePolicy good = {.count=2, .ranges={{0x806b40,0x807000},{0x808e40,0x809700}}};
    assert(lfj8_h03_service_span_allowed(&good,0x806b3f,1));
    assert(!lfj8_h03_service_span_allowed(&good,0x806b3f,2));
    assert(!lfj8_h03_service_span_allowed(&good,0x806b40,1));
    assert(!lfj8_h03_service_span_allowed(&good,0x806fff,1));
    assert(lfj8_h03_service_span_allowed(&good,0x807000,1));
    assert(lfj8_h03_service_span_allowed(&good,UINT32_MAX,0));
    assert(!lfj8_h03_service_span_allowed(&good,UINT32_MAX,1));
    assert(!lfj8_h03_service_span_allowed(&good,0,UINT32_MAX));
    assert(!lfj8_h03_service_span_allowed(0,0,0));
    assert(lfj8_h03_service_copy_allowed(&good,0x806b40,100,0));
    assert(!lfj8_h03_service_copy_allowed(&good,0x806b3f,100,1));
    assert(!lfj8_h03_service_copy_allowed(&good,0x807000,1,2));
    assert(!lfj8_h03_service_copy_allowed(&good,UINT32_MAX-2,3,1));
    assert(lfj8_h03_service_copy_allowed(&good,0x807000,257,1));
    Lfj8H03ServicePolicy bad = good;
    bad.count=0; assert(!lfj8_h03_service_span_allowed(&bad,0,0));
    bad.count=9; assert(!lfj8_h03_service_span_allowed(&bad,0,0));
    bad=good;bad.ranges[1].first=0x806fff;assert(!lfj8_h03_service_span_allowed(&bad,0,1));
    bad=good;bad.ranges[0].first=0x803fff;assert(!lfj8_h03_service_span_allowed(&bad,0,1));
    bad=good;bad.ranges[0].end=bad.ranges[0].first;assert(!lfj8_h03_service_span_allowed(&bad,0,1));
    bad=good;bad.ranges[1].end=0x80a001;assert(!lfj8_h03_service_span_allowed(&bad,0,1));
    puts("H03 service policy: 20 boundary, overflow, original-span and invalid-policy assertions PASS");
    return 0;
}
