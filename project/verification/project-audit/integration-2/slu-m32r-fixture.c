#include "lfj8_h03_slu.h"
#include <assert.h>
#include <stdio.h>
static const unsigned xs[] = {2560,25600,25600,25600,25600,25600,25600,25600,25600,25600};
static const unsigned ys[] = {0,25600,25600,25600,25600,25600,25600,25600,25600,25600};

static unsigned expected(unsigned raw) {
    unsigned i=0;
    if (raw<=xs[0]) return ys[0];
    while (i+1<sizeof(xs)/sizeof(xs[0]) && raw>=xs[i+1]) ++i;
    if (i+1==sizeof(xs)/sizeof(xs[0])) return ys[i];
    return (ys[i]*(xs[i+1]-raw)+ys[i+1]*(raw-xs[i]))/(xs[i+1]-xs[i]);
}
int main(void) {
    for (unsigned raw=0;raw<65536u;++raw) {
        Lfj8H03SluInput input={.pressure_7136=(uint16_t)(25600u-raw),
            .selector_4544=0xa5,.flags_4828=0x80,.flags_4822=(raw&1)?0x80:0,.qualified=true};
        Lfj8H03SluCommand command;
        assert(lfj8_h03_slu_command(&input,&command));
        assert(command.selected_7246==raw && command.characteristic_7130==expected(raw));
        assert(command.force==((raw&1)!=0));
        input.qualified=false;
        assert(!lfj8_h03_slu_command(&input,&command));
        assert(command.selected_7246==0 && command.characteristic_7130==0 && !command.force);
    }
    puts("M32R SLU: 65536 words against pinned S01 curve, force and invalidation PASS");
    return 0;
}
void __init(void) {}
void __fini(void) {}
