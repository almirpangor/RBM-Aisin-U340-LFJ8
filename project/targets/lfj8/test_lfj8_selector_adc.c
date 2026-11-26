#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stddef.h>

#include "lfj8_selector_adc.h"
#include "rbm_u340e.h"

typedef struct {
    uint16_t hardware_raw;
    unsigned depth;
    unsigned reads;
} Fixture;

typedef void (*StockPublisher)(volatile Lfj8SelectorAdc *adc,
                               const Lfj8RegisterIo *io, uint8_t valid, uint32_t captured_us);

static uint32_t enter(void *context)
{
    Fixture *fixture = context;
    assert(fixture->depth++ == 0u);
    return 0x5Au;
}

static void leave(void *context, uint32_t saved_state)
{
    Fixture *fixture = context;
    assert(saved_state == 0x5Au && fixture->depth-- == 1u);
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *fixture = context;
    assert(fixture->depth == 1u && address == 0x804BC6u);
    ++fixture->reads;
    return fixture->hardware_raw;
}

static Lfj8RegisterIo register_io(Fixture *fixture)
{
    const Lfj8RegisterIo io = {
        .context = fixture,
        .read16 = read16,
        .enter = enter,
        .leave = leave,
    };
    return io;
}

static void expect(Lfj8SelectorAdcReading reading, Lfj8SelectorAdcEvent event, uint16_t raw)
{
    assert(reading.event == event && reading.raw == raw);
}

static void verify_publication_contract(StockPublisher publish)
{
    volatile Lfj8SelectorAdc mailbox;
    Fixture fixture = {.hardware_raw = 512u};
    const Lfj8RegisterIo io = register_io(&fixture);

    lfj8_selector_adc_init(&mailbox);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_NONE, UINT16_MAX);
    assert(fixture.reads == 0u);

    publish(&mailbox, &io, 1u, UINT32_MAX);
    const Lfj8SelectorAdcReading at_wrap = lfj8_selector_adc_take(&mailbox, &io);
    assert(at_wrap.captured_us == UINT32_MAX);
    expect(at_wrap, LFJ8_SELECTOR_ADC_VALUE, 512u);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_NONE, UINT16_MAX);
    assert(fixture.reads == 1u);

    publish(&mailbox, &io, 0u, 0u);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_INVALID, UINT16_MAX);
    assert(fixture.reads == 1u);

    lfj8_selector_adc_publish(&mailbox, &io, 1023u, 1u);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_VALUE, 1023u);
    lfj8_selector_adc_publish(&mailbox, &io, 1024u, 2u);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_INVALID, UINT16_MAX);
    lfj8_selector_adc_publish(&mailbox, &io, 0u, 3u);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_VALUE, 0u);

    lfj8_selector_adc_publish(&mailbox, &io, 347u, 4u);
    lfj8_selector_adc_publish(&mailbox, &io, UINT16_MAX, 5u);
    lfj8_selector_adc_publish(&mailbox, &io, 347u, 6u);
    const Lfj8SelectorAdcReading overrun = lfj8_selector_adc_take(&mailbox, &io);
    assert(overrun.captured_us == 6u);
    expect(overrun, LFJ8_SELECTOR_ADC_OVERRUN, UINT16_MAX);
    expect(lfj8_selector_adc_take(&mailbox, &io), LFJ8_SELECTOR_ADC_NONE, UINT16_MAX);
    assert(fixture.reads == 1u && fixture.depth == 0u);
}

static uint8_t consume(volatile Lfj8SelectorAdc *mailbox, const Lfj8RegisterIo *io,
                       RbmU340eSelectorInput *decoder, uint8_t position)
{
    const Lfj8SelectorAdcReading reading = lfj8_selector_adc_take(mailbox, io);
    return reading.event == LFJ8_SELECTOR_ADC_NONE
               ? position : rbm_u340e_selector_sample(decoder, reading.raw);
}

static void verify_four_distinct_events(StockPublisher publish)
{
    volatile Lfj8SelectorAdc mailbox;
    RbmU340eSelectorInput decoder = {0};
    Fixture fixture = {.hardware_raw = 347u};
    const Lfj8RegisterIo io = register_io(&fixture);
    uint8_t position = RBM_U340E_SELECTOR_UNKNOWN;
    uint32_t captured_us = 0;

    lfj8_selector_adc_init(&mailbox);
    publish(&mailbox, &io, 1u, captured_us++);
    for (unsigned poll = 0u; poll < 8u; ++poll) {
        position = consume(&mailbox, &io, &decoder, position);
        assert(position == RBM_U340E_SELECTOR_UNKNOWN);
    }
    for (unsigned event = 0u; event < 2u; ++event) {
        publish(&mailbox, &io, 1u, captured_us++);
        position = consume(&mailbox, &io, &decoder, position);
        assert(position == RBM_U340E_SELECTOR_UNKNOWN);
    }
    publish(&mailbox, &io, 1u, captured_us++);
    position = consume(&mailbox, &io, &decoder, position);
    assert(position == RBM_U340E_SELECTOR_2);
    assert(consume(&mailbox, &io, &decoder, position) == RBM_U340E_SELECTOR_2);

    publish(&mailbox, &io, 1u, captured_us++);
    publish(&mailbox, &io, 1u, captured_us++);
    position = consume(&mailbox, &io, &decoder, position);
    assert(position == RBM_U340E_SELECTOR_UNKNOWN);
    for (unsigned event = 0u; event < 3u; ++event) {
        publish(&mailbox, &io, 1u, captured_us++);
        position = consume(&mailbox, &io, &decoder, position);
        assert(position == RBM_U340E_SELECTOR_UNKNOWN);
    }
    publish(&mailbox, &io, 1u, captured_us++);
    position = consume(&mailbox, &io, &decoder, position);
    assert(position == RBM_U340E_SELECTOR_2);

    publish(&mailbox, &io, 0u, 0u);
    assert(consume(&mailbox, &io, &decoder, position) == RBM_U340E_SELECTOR_UNKNOWN);
    assert(fixture.reads == 10u && fixture.depth == 0u);
}

void verify_lfj8_selector_adc(void)
{
    verify_publication_contract(lfj8_selector_adc_publish_9e1b);
    verify_four_distinct_events(lfj8_selector_adc_publish_9e1b);
    verify_publication_contract(lfj8_selector_adc_publish_9e1c);
    verify_four_distinct_events(lfj8_selector_adc_publish_9e1c);
}
