#include "lfj8_h03_atf_feed.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static uint32_t read_atf(const FactoryHydraulics *gp)
{
    uint32_t value;
    assert(factory_hydraulics_get(gp, -7184, 2u, &value));
    return value;
}

static void check_frame(const Lfj8CheryTxInputs *inputs, uint8_t encoded_atf)
{
    uint8_t frame[8];
    lfj8_pack_300(frame, inputs->status0_300, inputs->status1_300, inputs->flag_fd18_9,
                  inputs->atf_c, inputs->atf_valid);
    assert(frame[0] == 0x12u && frame[1] == 0x34u && frame[2] == 0x40u);
    assert(frame[3] == encoded_atf);
    assert(inputs->stopped == 1u);
}

int main(void)
{
    FactoryHydraulics gp = {0};
    Lfj8CheryTxInputs tx = {
        .status0_300 = 0x12, .status1_300 = 0x34, .flag_fd18_9 = 1, .stopped = 1,
    };
    Lfj8H03AtfSample sample = {
        .acquired_us = 92u, .atf_c = 60, .toyota_gp_m7184 = 25664u,
    };
    uint32_t command_at = 96u;
    assert(lfj8_h03_atf_feed(&sample, 100u, 9u, &gp, &command_at, &tx));
    assert(read_atf(&gp) == 25664u && command_at == 92u);
    check_frame(&tx, 100u);

    sample.atf_c = 10;
    sample.toyota_gp_m7184 = 12800u;
    assert(!lfj8_h03_atf_feed(&sample, 100u, 8u, &gp, &command_at, &tx));
    assert(read_atf(&gp) == 25664u && command_at == 92u);
    check_frame(&tx, 0xffu);

    sample.acquired_us = UINT32_MAX - 3u;
    command_at = 2u;
    assert(lfj8_h03_atf_feed(&sample, 4u, 9u, &gp, &command_at, &tx));
    assert(read_atf(&gp) == 12800u && command_at == UINT32_MAX - 3u);
    check_frame(&tx, 50u);

    command_at = UINT32_MAX - 4u;
    assert(lfj8_h03_atf_feed(&sample, 4u, 9u, &gp, &command_at, NULL));
    assert(command_at == UINT32_MAX - 4u);

    command_at = 5u;
    sample.atf_c = -10;
    sample.toyota_gp_m7184 = 7680u;
    assert(!lfj8_h03_atf_feed(&sample, 4u, 9u, &gp, &command_at, &tx));
    assert(read_atf(&gp) == 12800u && command_at == 5u);
    check_frame(&tx, 30u);

    command_at = 3u;
    assert(!lfj8_h03_atf_feed(NULL, 4u, 9u, &gp, &command_at, &tx));
    assert(tx.atf_c == 0);
    check_frame(&tx, 0xffu);
    assert(!lfj8_h03_atf_feed(&sample, 4u, 0u, &gp, &command_at, &tx));
    assert(!lfj8_h03_atf_feed(&sample, 4u, UINT32_C(0x80000000), &gp, &command_at, &tx));
    sample.acquired_us = 5u;
    assert(!lfj8_h03_atf_feed(&sample, 4u, 9u, &gp, &command_at, &tx));
    assert(read_atf(&gp) == 12800u && command_at == 3u);
    check_frame(&tx, 0xffu);

    puts("h03 ATF feed: qualified GP, command age and Chery 0x300 OK");
    return 0;
}
