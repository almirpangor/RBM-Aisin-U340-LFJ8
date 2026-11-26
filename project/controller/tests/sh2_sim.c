#include <stddef.h>

void __assert_func(const char *file, int line, const char *function, const char *expression)
{
    (void)file;
    (void)line;
    (void)function;
    (void)expression;
    __asm__ volatile ("trapa #255");
    __builtin_unreachable();
}

void *memset(void *dst, int value, size_t size)
{
    unsigned char *target = dst;
    while (size--) {
        *target++ = (unsigned char)value;
    }
    return dst;
}

void *memcpy(void *dst, const void *src, size_t size)
{
    unsigned char *target = dst;
    const unsigned char *source = src;
    while (size--) {
        *target++ = *source++;
    }
    return dst;
}

int memcmp(const void *left, const void *right, size_t size)
{
    const unsigned char *a = left;
    const unsigned char *b = right;
    for (size_t i = 0; i < size; ++i) {
        if (a[i] != b[i]) {
            return (int)a[i] - (int)b[i];
        }
    }
    return 0;
}
