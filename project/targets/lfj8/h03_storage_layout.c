/* ABI probe and address-model storage, not an application initializer. */
#include "lfj8_h03_storage.h"
#include <stddef.h>
#include <stdint.h>

typedef struct {
    char name[32];
    uint32_t offset;
    uint32_t size;
    uint32_t alignment;
} LayoutRecord;

_Static_assert(sizeof(void *) == 4, "Use the target M32R ABI");
_Static_assert(sizeof(LayoutRecord) == 44, "Unexpected layout record padding");
#define COUNT_FIELD(name, type) + 1
enum { RECORDS = 3
    LFJ8_H03_CONTROL_FIELDS(COUNT_FIELD)
    LFJ8_H03_COMMUNICATION_FIELDS(COUNT_FIELD)
    LFJ8_H03_WORKSPACE_FIELDS(COUNT_FIELD) };
#undef COUNT_FIELD

#define CONTROL_ROW(name, type) {"control/" #name, offsetof(Lfj8H03ControlStorage, name), sizeof(type), _Alignof(type)},
#define COMM_ROW(name, type) {"communication/" #name, offsetof(Lfj8H03CommunicationStorage, name), sizeof(type), _Alignof(type)},
#define WORK_ROW(name, type) {"workspace/" #name, offsetof(Lfj8H03WorkspaceStorage, name), sizeof(type), _Alignof(type)},
const struct {
    uint32_t magic, version, pointer_bytes, count;
    LayoutRecord records[RECORDS];
} rbm_h03_layout __attribute__((section(".rbm_layout"), used)) = {
    0x52424d31u, 1, sizeof(void *), RECORDS,
    {
        {"control", 0, sizeof(Lfj8H03ControlStorage), _Alignof(Lfj8H03ControlStorage)},
        LFJ8_H03_CONTROL_FIELDS(CONTROL_ROW)
        {"communication", 0, sizeof(Lfj8H03CommunicationStorage), _Alignof(Lfj8H03CommunicationStorage)},
        LFJ8_H03_COMMUNICATION_FIELDS(COMM_ROW)
        {"workspace", 0, sizeof(Lfj8H03WorkspaceStorage), _Alignof(Lfj8H03WorkspaceStorage)},
        LFJ8_H03_WORKSPACE_FIELDS(WORK_ROW)
    }
};

Lfj8H03ControlStorage rbm_h03_control __attribute__((section(".bss.rbm_control")));
Lfj8H03CommunicationStorage rbm_h03_communication __attribute__((section(".bss.rbm_communication")));
Lfj8H03WorkspaceStorage rbm_h03_workspace __attribute__((section(".bss.rbm_workspace")));
