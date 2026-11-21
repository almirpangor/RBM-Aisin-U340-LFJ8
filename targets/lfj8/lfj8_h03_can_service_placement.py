"""Native H03 CAN service sources and RAM bindings for an address model."""

SERVICE_MODULES = (
    "lfj8_h03_can_monitor_revoke.c",
    "lfj8_h03_can_target.c",
    "lfj8_h03_target_service.c",
    "lfj8_h03_atf_feed.c",
)

SERVICE_RAM_FIELDS = {
    "rbm_h03_application": "control/application",
    "rbm_h03_sensor_state": "control/sensors",
    "rbm_h03_tml0_1mhz_qualified": "control/clock_qualified",
    "h03_can_owner": "communication/can_owner",
    "rbm_h03_can_service": "communication/can_service",
    "rbm_h03_can13": "communication/can13",
    "rbm_h03_dtc_target": "communication/dtc_target",
    "rbm_h03_fast_output": "communication/fast_output",
    "rbm_h03_can13_input": "workspace/can13_input",
    "rbm_h03_tx_input": "workspace/tx_input",
    "rbm_h03_torque_input": "workspace/torque_input",
}


def typed_alias_ranges(storage, fields=SERVICE_RAM_FIELDS):
    """Resolve aliases in an independently validated M32R storage inventory."""
    ranges = {}
    for symbol, field_name in fields.items():
        group = field_name.split("/", 1)[0]
        field = storage["fields"][field_name]
        block = storage["blocks"][group]
        start = block["address"] + field["offset"]
        end = start + field["bytes"]
        alignment = field["alignment"]
        if (alignment <= 0 or alignment & (alignment - 1) or start % alignment or
                not block["address"] <= start < end <= block["end_exclusive"]):
            raise ValueError(f"The RAM address of {symbol} violates its typed block")
        if any(start < other_end and other_start < end for other_start, other_end in ranges.values()):
            raise ValueError(f"Overlapping native symbol {symbol}")
        ranges[symbol] = (start, end)
    return ranges
