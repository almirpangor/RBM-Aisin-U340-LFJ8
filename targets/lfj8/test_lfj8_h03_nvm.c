#include "lfj8_h03_nvm.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { SLOT_BYTES = 32, MARKER_OFFSET = 30, LARGE_BLOCK_BYTES = 0x10000 };
enum { COMPLETE, FAIL_BEFORE, FAIL_PARTIAL, FAIL_AFTER };

typedef struct {
    unsigned reads;
    unsigned changes;
    unsigned cut_on;
    unsigned cut_mode;
    unsigned erase_prefix;
    unsigned fail_read;
    unsigned mismatch_read;
    bool idle;
} Fixture;

/* Separate full-size erase blocks with the geometry of H03 blocks 4 and 7.
 * Their addresses are simulator inputs, not assignments for the hardware. */
static uint8_t flash[2][LARGE_BLOCK_BYTES];
static const uint32_t address[2] = {0x006000u, 0x020000u};
static const uint32_t length[2] = {0x2000u, 0x10000u};

static bool read_array(void *context, uint32_t first, uint8_t *data, size_t size)
{
    Fixture *fixture = context;
    const unsigned slot = first == address[0] ? 0u : 1u;
    assert(first == address[slot] && size == SLOT_BYTES);
    if (++fixture->reads == fixture->fail_read) {
        return false;
    }
    memcpy(data, flash[slot], size);
    if (fixture->reads == fixture->mismatch_read) {
        data[15] ^= 1u;
    }
    return true;
}

static bool allow_write(void *context, unsigned block)
{
    Fixture *fixture = context;
    assert(block == 4u || block == 7u);
    return fixture->idle;
}

static unsigned cut_mode(Fixture *fixture)
{
    assert(fixture->idle);
    return ++fixture->changes == fixture->cut_on ? fixture->cut_mode : COMPLETE;
}

static bool erase_block(void *context, uint32_t last_even)
{
    Fixture *fixture = context;
    const unsigned slot = last_even == address[0] + length[0] - 2u ? 0u : 1u;
    assert(last_even == address[slot] + length[slot] - 2u);
    const unsigned cut = cut_mode(fixture);
    if (cut != FAIL_BEFORE) {
        const size_t size = cut == FAIL_PARTIAL ? fixture->erase_prefix : length[slot];
        assert(size <= length[slot]);
        memset(flash[slot], 0xff, size);
    }
    return cut == COMPLETE;
}

static bool program_halfword(void *context, uint32_t first, uint16_t value)
{
    Fixture *fixture = context;
    const unsigned slot = first < address[1] ? 0u : 1u;
    const uint32_t offset = first - address[slot];
    assert(offset <= MARKER_OFFSET && (offset & 1u) == 0u);
    uint8_t *target = flash[slot] + offset;
    assert(target[0] == UINT8_MAX && target[1] == UINT8_MAX && value != UINT16_MAX);
    const unsigned cut = cut_mode(fixture);
    if (cut != FAIL_BEFORE) {
        target[0] = (uint8_t)(value >> 8);
        if (cut != FAIL_PARTIAL) {
            target[1] = (uint8_t)value;
        }
    }
    return cut == COMPLETE;
}

static Lfj8H03Nvm medium(Fixture *fixture)
{
    return (Lfj8H03Nvm){
        .context = fixture, .blocks = {4u, 7u}, .read = read_array, .allow_write = allow_write,
        .erase = erase_block, .program = program_halfword,
    };
}

static CheryDtcState history(void)
{
    CheryDtcState state;
    chery_dtc_init(&state);
    assert(chery_dtc_raise_c0(&state, 0x14u, false));
    return state;
}

static void expect_history(const CheryDtcState *got, const CheryDtcState *want)
{
    assert(memcmp(got->history, want->history, sizeof got->history) == 0);
    assert(memcmp(got->snapshot_index, want->snapshot_index, sizeof got->snapshot_index) == 0);
}

static void expect_empty(const CheryDtcState *state)
{
    CheryDtcState empty;
    chery_dtc_init(&empty);
    expect_history(state, &empty);
    assert(!state->clear_pending);
    assert(memcmp(state->current, empty.current, sizeof state->current) == 0);
}

static void install_record(unsigned slot, const CheryDtcState *state, uint32_t generation)
{
    assert(chery_dtc_journal_encode(state, generation, flash[slot]));
    flash[slot][29] = UINT8_MAX;
    flash[slot][30] = flash[slot][31] = 0u;
}

static void request_clear(Lfj8H03Nvm *nvm, CheryDtcState *live, bool success)
{
    const CheryDtcSession session = {.mode_bits = 0x90u, .permission_bits = 0x08u};
    const CheryDtcClearStore store = {lfj8_h03_nvm_commit_empty_dtc, nvm};
    const uint8_t request[3] = {0x14u, 0xffu, 0u};
    uint8_t reply[3] = {0};
    size_t size = 10u;
    const CheryDtcState before = *live;
    const CheryDtcResult result = chery_dtc_respond_with_store(
        live, session, request, sizeof request, reply, sizeof reply, &size, &store);
    if (!success) {
        assert(result == CHERY_DTC_STORAGE_FAILURE && size == 0u);
        assert(memcmp(live, &before, sizeof before) == 0);
        return;
    }
    assert(result == CHERY_DTC_REPLIED && size == 3u);
    assert(reply[0] == 0x54u && reply[1] == 0xffu && reply[2] == 0u);
    assert(live->clear_pending);
}

static void check_layout_and_restart(void)
{
    Fixture fixture = {.idle = true};
    Lfj8H03Nvm nvm = medium(&fixture);
    Lfj8H03NvmBlock block;
    for (unsigned i = 0; i < 2u; ++i) {
        assert(lfj8_h03_nvm_block(nvm.blocks[i], &block));
        assert(block.first == address[i] && block.end - block.first == length[i]);
    }
    assert(!lfj8_h03_nvm_block(LFJ8_H03_NVM_BLOCK_COUNT, &block));

    memset(flash, 0xff, sizeof flash);
    const CheryDtcState learned = history();
    CheryDtcState state = learned;
    nvm.blocks[1] = nvm.blocks[0];
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_INVALID);
    expect_empty(&state);
    assert(!lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.reads == 0u);

    nvm = medium(&fixture);
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_EMPTY);
    expect_empty(&state);
    fixture.idle = false;
    assert(!lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.changes == 0u);
    fixture.idle = true;
    CheryDtcState invalid = learned;
    invalid.snapshot_index[0] = CHERY_DTC_INDEX_COUNT;
    assert(!lfj8_h03_nvm_save_dtc(&nvm, &invalid) && fixture.changes == 0u);
    assert(lfj8_h03_nvm_save_dtc(&nvm, &learned));
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_SLOT_0);
    expect_history(&state, &learned);
    assert(state.current[2] == 0u && !state.clear_pending);
    const unsigned written = fixture.changes;
    assert(lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.changes == written);

    install_record(0u, &learned, UINT32_MAX);
    state = learned;
    request_clear(&nvm, &state, true);
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_SLOT_1);
    expect_empty(&state);
    for (unsigned i = 4u; i < 8u; ++i) {
        assert(flash[1][i] == 0u);
    }
}

static unsigned check_interrupted_clear(void)
{
    Fixture fixture = {.idle = true};
    Lfj8H03Nvm nvm = medium(&fixture);
    const CheryDtcState learned = history();
    CheryDtcState state = learned;
    memset(flash, 0xff, sizeof flash);
    install_record(0u, &learned, 1u);
    request_clear(&nvm, &state, true);
    const unsigned clear_changes = fixture.changes;
    assert(clear_changes <= 17u && clear_changes > 2u);

    for (unsigned cut = 1u; cut <= clear_changes; ++cut) {
        for (unsigned mode = FAIL_BEFORE; mode <= FAIL_AFTER; ++mode) {
            memset(flash[1], 0xff, length[1]);
            fixture = (Fixture){.idle = true, .cut_on = cut, .cut_mode = mode, .erase_prefix = 31u};
            state = learned;
            request_clear(&nvm, &state, false);
            assert(fixture.changes == cut);
            const Lfj8H03NvmResult result = lfj8_h03_nvm_restore_dtc(&nvm, &state);
            if (cut < clear_changes || mode == FAIL_BEFORE) {
                assert(result == LFJ8_H03_NVM_SLOT_0);
                expect_history(&state, &learned);
            } else {
                assert(result == (mode == FAIL_PARTIAL ? LFJ8_H03_NVM_CORRUPT : LFJ8_H03_NVM_SLOT_1));
                expect_empty(&state);
            }
        }
    }
    return clear_changes * 3u;
}

static void check_after_durable_clear(void)
{
    Fixture fixture = {.idle = true};
    Lfj8H03Nvm nvm = medium(&fixture);
    const CheryDtcState learned = history();
    CheryDtcState empty, state;
    chery_dtc_init(&empty);
    memset(flash, 0xff, sizeof flash);
    install_record(1u, &empty, 2u);
    flash[1][length[1] - 1u] = 0x57u;

    for (unsigned prefix = 0u; prefix <= SLOT_BYTES; ++prefix) {
        install_record(0u, &learned, 1u);
        fixture = (Fixture){.idle = true, .cut_on = 1u, .cut_mode = FAIL_PARTIAL, .erase_prefix = prefix};
        assert(!lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.changes == 1u);
        const Lfj8H03NvmResult result = lfj8_h03_nvm_restore_dtc(&nvm, &state);
        assert(result == LFJ8_H03_NVM_SLOT_1 || result == LFJ8_H03_NVM_CORRUPT);
        expect_empty(&state);
        assert(flash[1][length[1] - 1u] == 0x57u);
    }

    install_record(0u, &learned, 1u);
    for (unsigned offset = 0u; offset < SLOT_BYTES; ++offset) {
        for (unsigned bit = 0u; bit < 8u; ++bit) {
            const uint8_t mask = (uint8_t)(1u << bit);
            flash[1][offset] ^= mask;
            assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_CORRUPT);
            expect_empty(&state);
            assert(!lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.changes == 1u);
            flash[1][offset] ^= mask;
        }
    }
}

static void check_read_back_and_retry(void)
{
    Fixture fixture = {.idle = true, .mismatch_read = 4u};
    Lfj8H03Nvm nvm = medium(&fixture);
    const CheryDtcState learned = history();
    CheryDtcState state = learned;
    memset(flash, 0xff, sizeof flash);
    install_record(0u, &learned, 1u);
    request_clear(&nvm, &state, false);
    assert(flash[1][MARKER_OFFSET] == UINT8_MAX);

    fixture = (Fixture){.idle = true, .fail_read = 5u};
    request_clear(&nvm, &state, false);
    assert(flash[1][MARKER_OFFSET] == 0u);
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_SLOT_1);
    expect_empty(&state);
    const unsigned written = fixture.changes;
    request_clear(&nvm, &state, true);
    assert(fixture.changes == written);

    fixture.fail_read = fixture.reads + 2u;
    state = learned;
    assert(lfj8_h03_nvm_restore_dtc(&nvm, &state) == LFJ8_H03_NVM_READ_FAILED);
    expect_empty(&state);
    fixture.fail_read = fixture.reads + 2u;
    assert(!lfj8_h03_nvm_save_dtc(&nvm, &learned) && fixture.changes == written);
}

int main(void)
{
    printf("H03 erase ends:");
    for (unsigned i = 0; i < LFJ8_H03_NVM_BLOCK_COUNT; ++i) {
        Lfj8H03NvmBlock block;
        assert(lfj8_h03_nvm_block(i, &block));
        printf(" %05lX", (unsigned long)(block.end - 2u));
    }
    putchar('\n');
    check_layout_and_restart();
    const unsigned clear_cuts = check_interrupted_clear();
    check_after_durable_clear();
    check_read_back_and_retry();
    printf("H03 DTC NVM: %u write cuts, 33 erase prefixes, 256 bit faults and restart PASS\n", clear_cuts);
    return 0;
}
