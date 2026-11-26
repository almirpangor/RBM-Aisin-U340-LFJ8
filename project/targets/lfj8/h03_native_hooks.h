#ifndef RBM_H03_NATIVE_HOOKS_H
#define RBM_H03_NATIVE_HOOKS_H

/* Use the legacy decision only in the explicitly enabled bench build on
 * intact Mazda hardware. On converted hardware choose OEM or HANDLED.
 */
#define RBM_H03_HOOK_LEGACY_BENCH 0
#define RBM_H03_HOOK_OEM 1
#define RBM_H03_HOOK_HANDLED 2

#ifndef __ASSEMBLER__
/* OEM delegates one step to the original arbiter or driver. HANDLED returns
 * directly after a complete operation or an independently verified inhibit.
 * Each callback must restore its interrupt state before returning.
 */
int rbm_h03_strategy_callback(void);
int rbm_h03_commit_callback(void);
#endif

#endif
