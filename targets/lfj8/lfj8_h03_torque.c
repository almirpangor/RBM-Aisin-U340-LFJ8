#include "lfj8_h03_torque.h"

#include <stddef.h>

#include "factory_hydraulics.h"

enum {
    CANCEL = 0, START = 1, REFRESH = 2,
    STATUS_MAX_AGE = 100000u, PROGRESS_TIMEOUT = 60000u, SEND_INTERVAL = 20000u,
    DURATION_UNIT = 10000u, COOLDOWN = 350000u, RELEASE_TIMEOUT = 500000u,
};

static uint8_t crc8(const uint8_t *data)
{
    uint8_t crc = 0xff;
    for (unsigned i = 0; i < 7; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1du : 0u));
        }
    }
    return (uint8_t)(crc ^ 0xffu);
}

bool lfj8_h03_torque_demand(const FactoryHydraulics *gp, Lfj8TorqueDemand *demand)
{
    uint32_t flags, level, entry;
    if (!demand) {
        return false;
    }
    *demand = (Lfj8TorqueDemand){0};
    if (!gp || !factory_hydraulics_get(gp, -4833, 1, &flags) ||
        !factory_hydraulics_get(gp, -4520, 1, &level) ||
        !factory_hydraulics_get(gp, -9660, 4, &entry) || level > 7u) {
        return false;
    }
    if (!(flags & 0x10u)) {
        return true;
    }
    demand->active = 1;
    demand->level = (uint8_t)level;
    const unsigned gear = (entry >> 3) & 3u;
    const unsigned phase = entry & 7u;
    if (!(flags & 0x20u) && !(entry & 0x880u) && gear < 3u && (phase == 3u || phase == 4u)) {
        const unsigned up = (entry & 32u) != 0u;
        demand->from_gear = (uint8_t)(gear + 2u - up);
        demand->to_gear = (uint8_t)(gear + 1u + up);
    }
    return true;
}

void lfj8_h03_torque_init(Lfj8H03Torque *link)
{
    *link = (Lfj8H03Torque){0};
}

static bool running(const Lfj8H03Torque *link)
{
    return link->phase == LFJ8_TORQUE_WAITING || link->phase == LFJ8_TORQUE_ACTIVE;
}

static uint32_t pulse_duration_us(const Lfj8H03Torque *link)
{
    return (uint32_t)link->profile.duration * DURATION_UNIT;
}

static bool progress_timed_out(const Lfj8H03Torque *link, uint32_t at_us)
{
    const uint32_t last_progress = link->have_ack ? link->progress_at : link->started_at;
    return at_us - last_progress >= PROGRESS_TIMEOUT;
}

static void release(Lfj8H03Torque *link, bool failed, uint32_t now_us)
{
    link->full_reduction = false;
    link->failed = link->failed || failed;
    if (link->phase != LFJ8_TORQUE_RELEASING) {
        link->release_at = now_us;
        link->phase = link->tx_seq ? LFJ8_TORQUE_RELEASING : LFJ8_TORQUE_FAILED;
    }
}

static bool fresh(const Lfj8TorqueInput *input, uint32_t now_us)
{
    return input && now_us - input->captured_at_us < STATUS_MAX_AGE;
}

static bool permitted(const Lfj8TorqueInput *input)
{
    return input->permitted && input->engine_rpm >= 1200u && input->engine_rpm <= 6500u;
}

static bool admits_level(Lfj8TorqueProfile profile, unsigned level)
{
    return level > 0u && level < 8u && (profile.levels & (1u << level)) != 0u;
}

static const Lfj8TorqueProfile *shift_profile(const Lfj8TorqueCalibration *cal, unsigned from, unsigned to)
{
    if (!cal || from < 1u || from > 4u || to < 1u || to > 4u) {
        return NULL;
    }
    if (from + 1u == to) {
        return &cal->up[from - 1u];
    }
    if (to + 1u == from) {
        return &cal->down[to - 1u];
    }
    return NULL;
}

static void begin(Lfj8H03Torque *link, const Lfj8TorqueInput *input,
                  const Lfj8TorqueCalibration *cal, uint32_t now_us)
{
    unsigned from = input->demand.from_gear;
    unsigned to = input->demand.to_gear;
    const Lfj8TorqueProfile *profile = shift_profile(cal, from, to);
    if (!profile || input->observed_gear != from ||
        !admits_level(*profile, input->demand.level) || profile->reduction_q8 < 1u ||
        profile->reduction_q8 > 64u || profile->duration < 1u || profile->duration > 30u ||
        !link->have_status || now_us - link->last_status_at >= STATUS_MAX_AGE ||
        link->status_reduction || (link->status_phase >= 1u && link->status_phase <= 3u)) {
        return;
    }
    const unsigned token = (uint16_t)(link->status_token + 1u);
    link->token = (uint16_t)(token ? token : 1u);
    link->started_at = now_us;
    link->phase = LFJ8_TORQUE_WAITING;
    link->profile = *profile;
    link->from_gear = (uint8_t)from;
    link->to_gear = (uint8_t)to;
    link->seq = link->tx_seq = link->releases = 0;
    link->have_ack = link->failed = link->reached_full = link->full_reduction = false;
    link->cooling_down = true;
}

static void send_due(Lfj8H03Torque *link, uint32_t now_us, Lfj8TorqueSubmit submit, void *context)
{
    if (!submit || link->pending) {
        return;
    }
    unsigned op;
    if (link->phase == LFJ8_TORQUE_RELEASING) {
        if (link->releases >= 3u || (link->releases && now_us - link->submitted_at < SEND_INTERVAL)) {
            return;
        }
        op = CANCEL;
    } else {
        if (!running(link) || (link->tx_seq && now_us - link->submitted_at < SEND_INTERVAL) ||
            (link->phase == LFJ8_TORQUE_WAITING && link->tx_seq)) {
            return;
        }
        op = link->phase == LFJ8_TORQUE_WAITING ? START : REFRESH;
    }
    const uint8_t next = (uint8_t)(link->tx_seq + 1u);
    uint8_t bytes[8] = {0xa4, (uint8_t)op, next,
                        op ? link->profile.reduction_q8 : 0, op ? link->profile.duration : 0,
                        (uint8_t)link->token, (uint8_t)(link->token >> 8), 0};
    bytes[7] = crc8(bytes);
    if (!submit(context, LFJ8_TORQUE_REQUEST_ID, bytes)) {
        return;
    }
    link->tx_seq = next;
    link->submitted_at = now_us;
    link->pending = true;
    if (op == CANCEL && link->releases++ == 0) {
        link->first_release_seq = next;
    }
}

void lfj8_h03_torque_poll(Lfj8H03Torque *link, const Lfj8TorqueInput *input,
                         const Lfj8TorqueCalibration *cal, uint32_t now_us,
                         Lfj8TorqueSubmit submit, void *context)
{
    const uint32_t elapsed = now_us - link->started_at;
    const uint32_t duration = pulse_duration_us(link);
    if (elapsed >= duration + COOLDOWN) {
        link->cooling_down = false;
    }
    bool is_fresh = fresh(input, now_us);
    bool eligible = is_fresh && permitted(input);
    if (running(link)) {
        const Lfj8TorqueProfile *profile = shift_profile(cal, link->from_gear, link->to_gear);
        const bool same_profile = profile && profile->levels == link->profile.levels &&
                                  profile->reduction_q8 == link->profile.reduction_q8 &&
                                  profile->duration == link->profile.duration;
        bool same_demand = is_fresh && input->demand.active && input->demand.from_gear == link->from_gear &&
                           input->demand.to_gear == link->to_gear &&
                           admits_level(link->profile, input->demand.level);
        const bool timed_out = progress_timed_out(link, now_us);
        if (!eligible || !same_profile || timed_out || !same_demand || elapsed >= duration) {
            release(link, timed_out || !eligible || !same_profile, now_us);
        }
    }
    if (link->phase == LFJ8_TORQUE_RELEASING && now_us - link->release_at >= RELEASE_TIMEOUT) {
        link->phase = LFJ8_TORQUE_FAILED;
    }
    if (!is_fresh) {
        link->armed = false;
    } else {
        if (!input->demand.active) {
            link->armed = true;
        } else if (link->armed) {
            link->armed = false;
            if (eligible && !link->pending && !running(link) && link->phase != LFJ8_TORQUE_RELEASING &&
                !link->cooling_down) {
                begin(link, input, cal, now_us);
            }
        }
    }
    send_due(link, now_us, submit, context);
}

void lfj8_h03_torque_tx_done(Lfj8H03Torque *link, bool transmitted, uint32_t now_us)
{
    if (!link->pending) {
        return;
    }
    link->pending = false;
    if (transmitted) {
        link->seq = link->tx_seq;
    } else if (running(link) || link->phase == LFJ8_TORQUE_RELEASING) {
        release(link, true, now_us);
    }
}

bool lfj8_h03_torque_receive(Lfj8H03Torque *link, uint16_t standard_id, unsigned dlc,
                            const uint8_t *data, uint32_t received_at_us)
{
    if (standard_id != LFJ8_TORQUE_STATUS_ID || dlc != 8u || !data || data[0] != 0xa4u ||
        crc8(data) != data[7] || (data[1] & 15u) > 5u || data[1] >= 128u || data[3] > 64u ||
        data[6] > 8u || (link->have_status && received_at_us - link->last_status_at > INT32_MAX)) {
        return false;
    }
    const unsigned ecu_phase = data[1] & 15u;
    const unsigned token = data[4] | ((unsigned)data[5] << 8);
    const unsigned behind = (uint8_t)(link->seq - data[2]);
    const bool ecu_active = ecu_phase >= 1u && ecu_phase <= 3u;
    link->have_status = true;
    link->last_status_at = received_at_us;
    link->status_token = (uint16_t)token;
    link->status_phase = (uint8_t)ecu_phase;
    link->status_reduction = data[3];

    if (token != link->token) {
        if ((running(link) || link->phase == LFJ8_TORQUE_RELEASING) && (ecu_active || link->have_ack)) {
            /* A different owner or an engine reset invalidates this pulse. */
            link->phase = LFJ8_TORQUE_FAILED;
            link->full_reduction = false;
        }
        return true;
    }
    if (running(link) && link->seq && data[2] && behind <= 3u &&
        received_at_us - link->started_at <= INT32_MAX) {
        /* CAN13 delivers RX before poll. Apply both deadlines to the
         * capture time before updating the pulse's progress or result. */
        const bool timed_out = progress_timed_out(link, received_at_us);
        if (timed_out || received_at_us - link->started_at >= pulse_duration_us(link)) {
            release(link, timed_out, received_at_us);
            return true;
        }
        const unsigned progress = (uint8_t)(data[2] - link->ack_seq);
        if (link->have_ack && progress > 4u) {
            return true;
        }
        if (ecu_phase != 1u && ecu_phase != 2u) {
            release(link, true, received_at_us);
            return true;
        }
        if (!link->have_ack || progress) {
            link->progress_at = received_at_us;
        }
        link->ack_seq = data[2];
        link->phase = LFJ8_TORQUE_ACTIVE;
        link->have_ack = true;
        link->full_reduction = ecu_phase == 2u && (data[1] >> 4) == 7u &&
                               data[3] == link->profile.reduction_q8 && data[6] == 0u;
        if (link->full_reduction) {
            link->reached_full = true;
        }
    } else if (link->phase == LFJ8_TORQUE_RELEASING && link->releases &&
               (uint8_t)(data[2] - link->first_release_seq) < link->releases && behind <= 2u &&
               !data[3] && !ecu_active) {
        link->phase = link->failed || !link->reached_full || ecu_phase == 5u ||
                      (data[6] != 0u && data[6] != 8u) ? LFJ8_TORQUE_FAILED : LFJ8_TORQUE_COMPLETE;
    }
    return true;
}

bool lfj8_h03_torque_applied(const Lfj8H03Torque *link, uint32_t now_us)
{
    return link->phase == LFJ8_TORQUE_ACTIVE && link->full_reduction &&
           now_us - link->progress_at < PROGRESS_TIMEOUT &&
           now_us - link->started_at < pulse_duration_us(link);
}
