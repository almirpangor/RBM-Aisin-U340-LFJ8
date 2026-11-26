/* Immutable pre-projection startup bytes from S01 BSS reset
 * 0x012DA0..0x012DBA. All input mappings are verified against the
 * specified S01 ROM and its 0x0540B0 initialization. The two read-only
 * snapshots overlap each other because their bytes are identical.
 * Runtime and its mutable cold workspace remain disjoint. */
.section .rodata.h03_s01_cold_seed,"a",@progbits
.p2align 2
.global rbm_h03_target_startup_gear
.global rbm_h03_target_startup_gp
.type rbm_h03_target_startup_gear,@object
.type rbm_h03_target_startup_gp,@object
rbm_h03_target_startup_gear:
rbm_h03_target_startup_gp:
.zero 561
.size rbm_h03_target_startup_gear,360
.size rbm_h03_target_startup_gp,561
