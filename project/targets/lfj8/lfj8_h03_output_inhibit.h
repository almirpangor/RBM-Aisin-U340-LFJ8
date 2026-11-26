#ifndef RBM_LFJ8_H03_OUTPUT_INHIBIT_H
#define RBM_LFJ8_H03_OUTPUT_INHIBIT_H

/* H03 callback for Lfj8H03TakeoverOps.inhibit. Install only with commissioned
 * authority over D/E/F, Pressure A, and TIO9/P97 registers and verified
 * wiring isolation of spare outputs. TIO9 removal affects the pin mux,
 * latch and retained proposal, with physical inhibition still external.
 * Called under the takeover IRQ lock while its code and actuator RAM are live.
 * Withdraw authority and revoke under that lock before service takes over
 * registers or flash. Gate further takeover calls until ownership is restored.
 * The owner supplies independent hardware inhibition if execution stops.
 * Validate the OEM low-level state electrically and hydraulically on the
 * target installation before commissioning. */
void lfj8_h03_output_inhibit_locked(void *context);

#endif
