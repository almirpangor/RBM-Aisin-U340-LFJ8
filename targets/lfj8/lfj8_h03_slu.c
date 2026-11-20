#include "lfj8_h03_slu.h"

#include "factory_core.h"

bool lfj8_h03_slu_command(const Lfj8H03SluInput *input, Lfj8H03SluCommand *command)
{
    if (!command) {
        return false;
    }
    if (!input || !input->qualified) {
        command->selected_7246 = 0u;
        command->characteristic_7130 = 0u;
        command->force = false;
        return false;
    }

    uint16_t selected = (input->flags_4834 & 0x40u) ? 25600u : 2560u;
    if ((input->selector_4544 == 0xa5u || (input->flags_4834 & 0x08u)) &&
        ((input->flags_4828 & 0x80u) || (input->flags_4827 & 0x01u) || (input->flags_4829 & 0x18u))) {
        /* The original stores the subtraction as an unsigned 16-bit word. */
        selected = (input->flags_4825 & 0x08u) ? 2560u : (uint16_t)(25600u - input->pressure_7136);
    }
    command->selected_7246 = selected;
    command->characteristic_7130 = factory_slu_characteristic(selected);
    command->force = (input->flags_4822 & 0x80u) != 0u;
    return true;
}
