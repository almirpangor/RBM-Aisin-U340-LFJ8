#ifndef RBM_LFJ8_H03_INPUT_LIFECYCLE_H
#define RBM_LFJ8_H03_INPUT_LIFECYCLE_H

/* The application probes RAM ownership before reading its running flag.
 * Native input hooks call this under the same H03 interrupt exclusion. */
int lfj8_h03_application_running_locked(void);

#endif
