"""ST10 emission for read-only OBD DTC/ISO-TP. Private storage is C_CAN only.

Objects 7..10 cache complete response frames before any is transmitted.
Every cached frame is rebuilt from OEM DTCs and compared before transmission.
This is a bounded repeated-read consistency check, not an atomic OEM snapshot.
"""

TP_STATE=0xEF44
TP_SID=0xEF46
TP_INDEX=0xEF48
TP_COUNT=0xEF4A
TP_TIMER=0xEF4C # Bits15:7 = 9-bit timer; bits6:4 reserved; bits3:0 RX phase.
TP_BS=0xEF4E
TP_STMIN=0xEF50
TP_REMAIN=0xEF52

# High bytes; all low bytes retain Bench C meanings. IF2M2 bit13 is reserved.
IDLE,BUILD,VERIFY_START,VERIFY_DONE,WAIT_FC,SEND_CF,WAIT_TX,FIRST_CF=range(8)

def emit(a):
    def hi(r,addr): a.full_ld(r,addr);a.shift(r,8);a.andi(r,0x0F if addr==TP_SID else 255)
    def sethi(addr,v): a.full_ld(12,addr);a.andi(12,255);a.ori(12,v<<8);a.full_st(addr,12)
    def puthi(addr,r):
        a.full_ld(12,addr);a.andi(12,255);a.shift(r,8,True);a.either(12,r);a.full_st(addr,12)
    def timer(v):
        a.full_ld(12,TP_TIMER);a.andi(12,15);a.ori(12,v<<7);a.full_st(TP_TIMER,12)
    def valid_dtc():
        a.physical(4,0xF0B56);a.cmp(4,0x2BDA);a.branch(3,'tp_not_ready')
        # Native pending-operation marker:0 idle,5A5A pending, not init magic.
        a.physical(4,0xF0B5C);a.cmp(4,0);a.branch(3,'tp_not_ready')
        a.physical(4,0xF2859,True);a.cmp(4,10);a.branch(14,'tp_not_ready')

    a.label('tp_tick')
    # Runs once on every initialized tick, even when telemetry has priority.
    a.full_ld(4,TP_TIMER);a.rr(5,4);a.shift(5,7);a.cmp(5,0);a.branch(2,'tp_tick_done')
    a.subi(4,128);a.full_st(TP_TIMER,4)
    a.label('tp_tick_done');a.ret()

    a.label('tp_start')
    a.cmp(10,1);a.branch(3,'bad_length')
    a.cmp(7,0x8000|(0x7DF<<2));a.branch(3,'tp_physical')
    a.ori(8,0x10) # Remember functional origin separately from the service nibble.
    a.label('tp_physical')
    puthi(TP_SID,8)
    a.ld(4,0xEF80);a.andi(4,0x03C0);a.cmp(4,0);a.branch(3,'tp_changed')
    valid_dtc()
    sethi(TP_INDEX,0);sethi(TP_COUNT,0)
    a.call('tp_make_frame')
    a.cmp(7,0);a.branch(3,'tp_not_ready')
    # R13 = number of selected DTCs. Cache count and first frame.
    a.rr(4,13);puthi(TP_COUNT,4)
    sethi(TP_STATE,BUILD);timer(500)
    a.branch(0,'tp_store_frame')

    a.label('tp_poll')
    # Called only when IF1 is free and TX object4 is idle. RX is serviced first.
    hi(4,TP_STATE);a.cmp(4,0);a.branch(2,'exit')
    a.full_ld(5,TP_TIMER);a.shift(5,7);a.cmp(5,0)
    a.branch(3,'tp_timer_live')
    a.cmp(4,SEND_CF);a.branch(3,'tp_abort')
    a.label('tp_timer_live')
    a.cmp(4,BUILD);a.branch(2,'tp_build_next')
    a.cmp(4,VERIFY_START);a.branch(2,'tp_verify_start')
    a.cmp(4,WAIT_FC);a.branch(2,'exit')
    a.cmp(4,SEND_CF);a.branch(2,'tp_cf')
    a.cmp(4,WAIT_TX);a.branch(2,'tp_tx_complete')
    a.cmp(4,FIRST_CF);a.branch(2,'tp_first_cf')
    a.branch(0,'exit')

    a.label('tp_build_next')
    valid_dtc();a.call('tp_make_frame');a.cmp(7,0);a.branch(3,'tp_not_ready')
    hi(4,TP_COUNT);a.cmpreg(4,13);a.branch(3,'tp_changed')
    a.label('tp_store_frame')
    a.st(0xEF1E,8);a.st(0xEF20,9);a.st(0xEF22,10);a.st(0xEF24,11)
    a.zero(0xEF18);a.set(0xEF1A,0xA000|(0x7E8<<2));a.set(0xEF1C,0x88)
    hi(6,TP_INDEX);a.rr(7,6);a.addi(7,7)
    a.set(0xEF12,0xB3);a.st(0xEF10,7)
    a.call('tp_last_index');a.cmpreg(6,5);a.branch(2,'tp_build_finished')
    a.addi(6,1);puthi(TP_INDEX,6);a.branch(0,'exit')
    a.label('tp_build_finished')
    sethi(TP_INDEX,0);sethi(TP_STATE,VERIFY_START);a.branch(0,'exit')

    a.label('tp_verify_start')
    hi(7,TP_INDEX);a.addi(7,7);a.set(0xEF12,0x03);a.st(0xEF10,7)
    sethi(TP_STATE,VERIFY_DONE);a.set(0xEF4C,7);a.branch(0,'exit')
    a.label('tp_verify_done')
    # Invoked after IF1.Busy clears, before any other user of IF1.
    a.full_ld(4,TP_TIMER);a.shift(4,7);a.cmp(4,0);a.branch(2,'tp_abort')
    valid_dtc();a.call('tp_make_frame');a.cmp(7,0);a.branch(3,'tp_not_ready')
    hi(4,TP_COUNT);a.cmpreg(4,13);a.branch(3,'tp_changed')
    for addr,r in ((0xEF1E,8),(0xEF20,9),(0xEF22,10),(0xEF24,11)):
        a.ld(4,addr);a.cmpreg(4,r);a.branch(3,'tp_changed')
    hi(6,TP_INDEX);a.call('tp_last_index');a.cmpreg(6,5);a.branch(2,'tp_verified')
    a.addi(6,1);puthi(TP_INDEX,6);sethi(TP_STATE,VERIFY_START);a.branch(0,'exit')
    a.label('tp_verified')
    # All response frames are already in message RAM, and remain immutable.
    a.imm(6,7);a.call('tp_transmit')
    hi(4,TP_COUNT);a.cmp(4,2);a.branch(15,'tp_abort')
    sethi(TP_INDEX,1);sethi(TP_STATE,WAIT_FC);timer(500);a.branch(0,'exit')

    a.label('tp_fc')
    # Only physical FC belongs to this connection. R7 holds received arb2.
    a.cmp(7,0x8000|(0x7E0<<2));a.branch(3,'exit')
    hi(4,TP_STATE);a.cmp(4,WAIT_FC);a.branch(2,'tp_fc_accept')
    # The peer may send the next FC before our next 2ms TX-complete poll.
    a.cmp(4,WAIT_TX);a.branch(3,'exit')
    hi(4,TP_BS);a.cmp(4,0);a.branch(2,'exit')
    hi(4,TP_REMAIN);a.cmp(4,0);a.branch(3,'exit')
    a.label('tp_fc_accept')
    a.ld(4,0xEF1E);a.rr(5,4);a.andi(4,255);a.shift(5,8)
    a.cmp(4,0x31);a.branch(2,'tp_fc_wait')
    a.cmp(4,0x30);a.branch(3,'tp_abort')
    puthi(TP_BS,5)
    hi(5,TP_BS);puthi(TP_REMAIN,5)
    a.ld(4,0xEF20);a.andi(4,255)
    a.cmp(4,127);a.branch(15,'tp_st_ms')
    a.cmp(4,0xF1);a.branch(8,'tp_abort');a.cmp(4,0xF9);a.branch(14,'tp_abort')
    a.imm(4,1);a.branch(0,'tp_st_store')
    a.label('tp_st_ms');a.addi(4,1);a.shift(4,1);a.addi(4,1)
    a.label('tp_st_store');puthi(TP_STMIN,4)
    hi(4,TP_INDEX);a.andi(4,15);puthi(TP_INDEX,4)
    sethi(TP_STATE,FIRST_CF);timer(500);a.branch(0,'exit')
    a.label('tp_fc_wait')
    hi(4,TP_INDEX);a.addi(4,16);a.cmp(4,64);a.branch(9,'tp_abort')
    puthi(TP_INDEX,4);timer(500);a.branch(0,'exit')

    a.label('tp_first_cf')
    # Bound the wait for the first frame (or previous block) to finish on wire.
    a.ld(4,0xEF80);a.andi(4,0x03C0);a.cmp(4,0);a.branch(3,'exit')
    # Also honor STmin across block boundaries, measured conservatively from FC.
    a.branch(0,'tp_cf_separation')
    a.label('tp_cf')
    # Give the previous CAN frame at least STmin after its TX request clears.
    a.ld(4,0xEF80);a.andi(4,0x03C0);a.cmp(4,0);a.branch(3,'exit')
    a.full_ld(4,TP_TIMER);a.shift(4,7);a.cmp(4,0);a.branch(3,'exit')
    hi(6,TP_INDEX);a.andi(6,15);a.rr(4,6);a.addi(6,7);a.call('tp_transmit')
    hi(6,TP_INDEX);a.andi(6,15);a.call('tp_last_index');a.cmpreg(6,5);a.branch(2,'tp_abort')
    a.addi(6,1);puthi(TP_INDEX,6)
    hi(4,TP_BS);a.cmp(4,0);a.branch(2,'tp_cf_delay')
    hi(4,TP_REMAIN);a.subi(4,1);puthi(TP_REMAIN,4)
    a.branch(0,'tp_cf_delay')
    a.label('tp_cf_delay')
    sethi(TP_STATE,WAIT_TX);timer(500);a.branch(0,'exit')
    a.label('tp_tx_complete')
    a.ld(4,0xEF80);a.andi(4,0x03C0);a.cmp(4,0);a.branch(3,'exit')
    hi(4,TP_BS);a.cmp(4,0);a.branch(2,'tp_cf_separation')
    hi(4,TP_REMAIN);a.cmp(4,0);a.branch(3,'tp_cf_separation')
    sethi(TP_STATE,WAIT_FC);timer(500);a.branch(0,'exit')
    a.label('tp_cf_separation')
    sethi(TP_STATE,SEND_CF)
    hi(4,TP_STMIN);a.shift(4,7,True);a.full_ld(12,TP_TIMER);a.andi(12,15)
    a.either(12,4);a.full_st(TP_TIMER,12);a.branch(0,'exit')

    a.label('tp_abort')
    sethi(TP_STATE,IDLE);timer(0);a.branch(0,'exit')
    a.label('tp_not_ready');a.imm(5,0x22);a.branch(0,'tp_error')
    a.label('tp_changed');a.imm(5,0x21)
    a.label('tp_error')
    a.full_ld(7,TP_SID);a.andi(7,0x1000)
    a.cmp(7,0);a.branch(2,'tp_error_physical')
    a.imm(7,0x8000|(0x7DF<<2))
    a.label('tp_error_physical')
    hi(8,TP_SID);sethi(TP_STATE,IDLE);timer(0);a.branch(0,'negative')

    a.label('tp_transmit')
    # R6 = cache object7..10. Write Control + TxRqst, keep cached data/arbitration.
    a.set(0xEF1C,0x8088);a.set(0xEF12,0x94);a.st(0xEF10,6);a.ret()

    a.label('tp_last_index')
    # 0..2 codes -> SF; 3..5 -> FF+CF; 6..9 -> FF+2CF; 10 -> FF+3CF.
    hi(5,TP_COUNT);a.cmp(5,2);a.branch(15,'tp_last_zero')
    a.cmp(5,5);a.branch(15,'tp_last_one');a.cmp(5,9);a.branch(15,'tp_last_two')
    a.imm(5,3);a.ret()
    for label,value in (('tp_last_zero',0),('tp_last_one',1),('tp_last_two',2)):
        a.label(label);a.imm(5,value);a.ret()

    a.label('tp_make_frame')
    # Re-read the bounded list for a specific response frame. No shared RAM writes.
    # R7 returns error, R13 total codes, R8..11 the complete 8-byte frame.
    # First determine number of selected records; second assemble requested slice.
    a.imm(13,0);a.imm(15,0)
    a.call('tp_walk_count')
    a.cmp(15,0);a.branch(3,'tp_frame_error')
    a.rr(14,13);a.shift(14,1,True);a.addi(14,2) # payload length
    for r in (8,9,10,11):a.imm(r,0)
    hi(4,TP_INDEX);a.andi(4,15)
    a.cmp(13,2);a.branch(14,'tp_frame_multi')
    a.rr(8,14);a.imm(14,0xFFFF) # byte placement offset: logical byte0 -> CAN byte1
    a.branch(0,'tp_frame_header')
    a.label('tp_frame_multi')
    a.cmp(4,0);a.branch(3,'tp_frame_cf')
    a.rr(8,14);a.shift(8,8,True);a.ori(8,0x10);a.imm(14,0xFFFE)
    a.branch(0,'tp_frame_header')
    a.label('tp_frame_cf')
    a.rr(8,4);a.ori(8,0x20)
    a.rr(14,4);a.shift(14,3,True);a.sub(14,4);a.subi(14,2) # start=7*i-1; subtract prefix1
    a.label('tp_frame_header')
    hi(6,TP_SID);a.addi(6,0x40);a.imm(4,0);a.call('tp_place_byte')
    a.rr(6,13);a.imm(4,1);a.call('tp_place_byte')
    a.imm(13,0);a.imm(15,0);a.call('tp_walk_data')
    a.label('tp_frame_error');a.rr(7,15);a.ret()

    for name,data in (('tp_walk_count',False),('tp_walk_data',True)):
        a.label(name)
        for slot in range(10):
            skip=f'{name}_skip_{slot}'
            a.physical(4,0xF2859,True);a.cmp(4,slot);a.branch(15,skip)
            a.imm(7,slot*72);a.call('tp_get_code')
            a.cmp(6,0);a.branch(2,skip)
            if data:
                # Retain full code in R7; byte placer only clobbers R4..6.
                a.rr(7,6);a.shift(6,8);a.rr(4,13);a.shift(4,1,True);a.addi(4,2)
                a.call('tp_place_byte')
                a.rr(6,7);a.andi(6,255);a.rr(4,13);a.shift(4,1,True);a.addi(4,3)
                a.call('tp_place_byte')
            a.addi(13,1);a.label(skip)
        a.ret()

    a.label('tp_get_code')
    # Input R7=slot byte offset. R6=selected SAE code or0. R15 sticky error.
    a.indexed(4,7,0x382E,0x3C);a.cmp(4,0);a.branch(2,'tp_code_zero')
    a.cmp(4,104);a.branch(14,'tp_code_error')
    a.indexed(6,7,0x3838,0x3C);a.andi(6,8);a.cmp(6,0);a.branch(2,'tp_code_zero')
    a.indexed(5,7,0x3833,0x3C,True)
    hi(6,TP_SID);a.cmp(6,3);a.branch(3,'tp_code_pending')
    a.cmp(5,10);a.branch(15,'tp_code_zero');a.branch(0,'tp_code_selected')
    a.label('tp_code_pending');a.cmp(5,10);a.branch(8,'tp_code_zero')
    a.cmp(5,12);a.branch(14,'tp_code_zero')
    a.label('tp_code_selected')
    a.indexed(5,7,0x3836,0x3C);a.shift(5,8);a.andi(5,15)
    a.indexed(5,5,0x3112,0x2E,True);a.cmp(5,3);a.branch(14,'tp_code_error')
    a.shift(4,3,True);a.shift(5,1,True);a.add(4,5)
    a.indexed(6,4,0x2BDA,0x2E);a.cmp(6,0);a.branch(2,'tp_code_error')
    a.cmp(6,0xFFFF);a.branch(2,'tp_code_error')
    a.ret()
    a.label('tp_code_error');a.imm(15,1)
    a.label('tp_code_zero');a.imm(6,0);a.ret()

    a.label('tp_place_byte')
    # Input R4 logical payload index, R6 byte, R14 logical-to-CAN offset.
    a.sub(4,14);a.cmp(4,0);a.branch(2,'tp_place_done')
    a.cmp(4,7);a.branch(14,'tp_place_done')
    for byte in range(8):
        a.cmp(4,byte);a.branch(2,f'tp_place_{byte}')
    a.branch(0,'tp_place_done')
    for byte in range(8):
        a.label(f'tp_place_{byte}')
        if byte&1:a.shift(6,8,True)
        a.either(8+byte//2,6);a.ret()
    a.label('tp_place_done');a.ret()
