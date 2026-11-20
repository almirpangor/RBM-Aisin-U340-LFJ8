#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_bridge.h"
#include "panel_pulse.h"
#include "rbm_u340e.h"
#include "ta2005_chery_inputs.h"

void verify_lfj8_selector_adc(void);

static RbmU340eOutput sample_buttons(RbmU340eController *controller,
    RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
}

static void print_payload(const uint8_t frame[8])
{
    for (unsigned int index = 0; index < 8; ++index) {
        printf("%02x", (unsigned int)frame[index]);
    }
}

static void parse_payload(const char *hex, uint8_t frame[8])
{
    assert(strlen(hex) == 16);
    for (unsigned int index = 0; index < 8; ++index) {
        unsigned int byte;
        int read = 0;
        assert(sscanf(hex + 2 * index, "%2x%n", &byte, &read) == 1 && read == 2);
        frame[index] = (uint8_t)byte;
    }
}

int main(int argc, char **argv)
{
    verify_lfj8_selector_adc();
    assert(argc == 1 || argc == 3);
    uint8_t rpm_frame[8] = {0x12, 0xc0, 0xff, 0xff, 0x00, 0xff, 0x00, 0x00};
    uint8_t coolant_frame[8] = {0xb4, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    if (argc == 3) {
        parse_payload(argv[1], rpm_frame);
        parse_payload(argv[2], coolant_frame);
    }
    Ta2005CheryInputs engine_receiver;
    Ta2005CherySnapshot engine_inputs;
    const uint32_t tick = 0;
    ta2005_chery_inputs_reset(&engine_receiver);
    assert(ta2005_chery_inputs_receive(&engine_receiver, 0x0fa, 8, rpm_frame, &tick));
    assert(ta2005_chery_inputs_receive(&engine_receiver, 0x278, 8, coolant_frame, &tick));
    assert(ta2005_chery_inputs_snapshot(&engine_receiver, &tick, 5, &engine_inputs) ==
           (TA2005_CHERY_SPEED | TA2005_CHERY_COOLANT));
    assert(engine_inputs.speed_fad8 == 9600 && engine_inputs.coolant_f9e9 == 137);

    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .overdrive_limit_modes = RBM_U340E_OVERDRIVE_TIPTRONIC,
        .initial_mode = RBM_U340E_AUTO,
        .initial_overdrive_enabled = 1,
    };
    RbmU340eController controller;
    assert(rbm_u340e_init(&controller, &policy));
    RbmU340eInput input = {
        .selector = RBM_U340E_SELECTOR_R,
        .buttons_valid = 1,
        .actual_gear = 2,
        .allowed_gears = 0x0F,
    };
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('R'));
    assert(lfj8_relay_mask('R') == 3);
    input.selector = RBM_U340E_SELECTOR_L;
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('L'));
    assert(lfj8_relay_mask('L') == 2);
    input.selector = RBM_U340E_SELECTOR_D;
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('D'));
    assert(lfj8_relay_mask('D') == 0);

    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 3);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 0);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_DOWN).requested_gear == 1);
    input.actual_gear = 3;
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE).overdrive_pressed);
    assert(!sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_AUTO);

    const uint16_t raw = lfj8_vss_raw_1ae(11000, 1, 100000, 2000000, 1, 1, LFJ8_VSS_VALID);
    assert(raw == 1440);
    const Lfj8Chery1ae fields = {
        .byte1 = 0xFF,
        .byte4 = 0xFF,
        .flag_e026_0 = 1,
    };
    uint8_t speed_frame[8];
    uint8_t atf_frame[8];
    assert(lfj8_pack_1ae(speed_frame, &fields, raw) == 0);
    lfj8_pack_300(atf_frame, 0, 0, 0, 84, 1);

    const PanelPulseConfig panel_config = {
        .timer_hz = 1000000,
        .minimum_pulses_per_km = 5000,
        .maximum_pulses_per_km = 7000,
        .high_permille = 500,
        .period_field_bits = 32,
        .period_encoding = PANEL_PERIOD_TICKS,
        .width_encoding = PANEL_WIDTH_HIGH_TICKS,
    };
    PanelPulse panel;
    assert(panel_pulse_init(&panel, &panel_config));
    const unsigned int speed_q7 = (raw / 25u) * 32u;
    const PanelOutput pulse = panel_pulse_plan(&panel, (uint16_t)(speed_q7 * 100u / 128u), true);
    assert(pulse.status == PANEL_OUTPUT_ACTIVE);
    assert(pulse.period_field == 42105);
    assert(pulse.width_field == 21053);

    printf("{\"speed_raw\":%u,\"0x1AE\":\"", (unsigned int)raw);
    print_payload(speed_frame);
    printf("\",\"0x300\":\"");
    print_payload(atf_frame);
    printf("\",\"panel_input_speed_q7\":%u,\"panel_period_ticks_1mhz\":%lu,"
           "\"tc_rx_rpm_q3\":%u,\"tc_rx_coolant_plus_50\":%u,\"selector_adc_events\":\"PASS\"}\n",
           speed_q7, (unsigned long)pulse.period_field,
           (unsigned int)engine_inputs.speed_fad8, (unsigned int)engine_inputs.coolant_f9e9);
    return 0;
}
