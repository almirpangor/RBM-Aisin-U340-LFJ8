"""E4 relative native-request intervention; exact GW4G15 revision only.

No Nm conversion is claimed. Request reduction is unsigned Q8, 1..64/256.
Three hooks reduce register operands before OEM arbitration continues.
Private state is reserved from the native R0 software stack, never guessed RAM.
Timing reads the existing GPT1 T4 / native overflow counter, without configuring it.
"""
ORIGIN, LIMIT = 0x64800, 0x67FFE
RAM, RAM_END = 0xE7C0, 0xE800
MAGIC, MODE, TOKEN, SEQ, RED, DURATION = range(RAM, RAM+12, 2)
START_LO, START_HI, RX_LO, RX_HI, PHASE, REASON = range(RAM+12,RAM+24,2)
SEEN, BEFORE, AFTER, DIV, READY, EPOCH = range(RAM+24,RAM+36,2)
GAP, BUSY_COUNT = RAM+36, RAM+38
TAG = 0xA4D2
LEASE = 3906       # 49.9968 ms at the existing 40 MHz CPU assumption / 512.
COOLDOWN = 23438   # 300.0064 ms; added to original requested duration.
PULSE_MAX = 23430  # 30 * 781 ticks, 299.904 ms nominal.
# Keep the requested duration separately when cancel shortens DURATION.
ORIGINAL_DURATION = RAM+40
CALL_AGE, START_CALL_AGE = RAM+42, RAM+44
HOOKS = ((0x595A8, '42f97c97', 'hook_air'),
         (0x5B0BE, 'f08742f75e97', 'hook_fast'),
         (0x5B5D6, 'f2f47c97', 'hook_load'))

def crc8(data):
    crc=0xFF
    for b in data:
        crc ^= b
        for _ in range(8):crc=((crc<<1)^0x1D if crc&128 else crc<<1)&255
    return crc^255

def command(op,seq,reduction,duration,token):
    d=bytes([0xA4,op,seq,reduction,duration,token&255,token>>8])
    return d+bytes([crc8(d)])

def assemble_torque(Base,far,word):
    class Asm(Base):
        def call(self,label):
            self.fix.append((len(self.data)+2,label));self.raw('ca000000','CALLA '+label)
        def ret(self):self.raw('cb00','RET')
        def rets(self):self.raw('db00','RETS')
        def push(self,r):self.emit(bytes([0xEC,0xF0+r]),'PUSH R'+str(r))
        def pop(self,r):self.emit(bytes([0xFC,0xF0+r]),'POP R'+str(r))
        def xor(self,d,s):self.op(0x50,d,s,'XOR')
        def xor_i(self,r,v):self.ri(0x56,r,v,'XOR')
        def can_byte(self,r,addr):
            # ST10F276 UM0404 21.1.1: CAN registers are word-access-only.
            # Extract a wire byte in a GPR after an aligned 16-bit bus read.
            assert 0xEF1E<=addr<=0xEF25
            self.ld(r,addr&~1)
            if addr&1:self.shift(r,8)
            else:self.andi(r,255)
    a=Asm(ORIGIN,LIMIT)
    # Called with R4..R15 and PSW already saved by E3 wrapper. Result R4:
    # 1 owns IF1 this tick; 0 lets the existing diagnostics/telemetry run.
    a.label('torque_tick')
    a.ld(4,MAGIC);a.cmp(4,TAG);a.branch(2,'tick_initialized')
    for addr in range(RAM,RAM_END,2):a.zero(addr)
    a.set(MAGIC,TAG)
    a.label('tick_initialized')
    a.ld(4,MODE);a.cmp(4,0);a.branch(2,'counter_done')
    for addr in (CALL_AGE,START_CALL_AGE):
        a.ld(4,addr);a.cmp(4,65535);a.branch(2,'sat_'+str(addr));a.addi(4,1);a.st(addr,4);a.label('sat_'+str(addr))
    a.label('counter_done')
    a.ld(4,0xEF10);a.andi(4,0x8000);a.branch(2,'if_ready')
    a.ld(4,BUSY_COUNT);a.addi(4,1);a.st(BUSY_COUNT,4);a.cmp(4,50);a.branch(8,'tick_owned')
    a.zero(MODE);a.set(REASON,7);a.set(0xEF00,0x61);a.branch(0,'tick_owned')
    a.label('if_ready');a.zero(BUSY_COUNT)
    a.ld(7,READY);a.cmp(7,2);a.branch(2,'io_ready')
    a.zero(0xEF18);a.zero(0xEF14);a.set(0xEF16,0xDFFC)
    a.cmp(7,0);a.branch(3,'init_tx')
    a.set(0xEF1A,0x8000|(0x5E8<<2));a.set(0xEF1C,0x1088)
    a.set(0xEF12,0xF3);a.set(0xEF10,11);a.set(READY,1);a.branch(0,'tick_owned')
    a.label('init_tx')
    a.set(0xEF1A,0xA000|(0x5E9<<2));a.set(0xEF1C,0x88)
    a.set(0xEF12,0xF3);a.set(0xEF10,12);a.set(READY,2);a.branch(0,'tick_owned')
    a.label('io_ready')
    a.ld(4,PHASE);a.cmp(4,1);a.branch(2,'receive_complete')
    a.ld(4,GAP);a.cmp(4,0);a.branch(2,'poll_rx')
    a.zero(GAP);a.imm(4,0);a.rets()
    a.label('poll_rx')
    a.ld(4,0xEF90);a.andi(4,1<<10);a.branch(2,'status_tick')
    a.set(0xEF12,0x37);a.set(0xEF10,11);a.set(PHASE,1);a.branch(0,'tick_owned')
    a.label('receive_complete');a.zero(PHASE);a.set(GAP,1)
    a.ld(4,0xEF1A);a.cmp(4,0x8000|(0x5E8<<2));a.branch(3,'reject_frame')
    a.ld(4,0xEF1C);a.andi(4,0xC00F);a.cmp(4,0x8008);a.branch(3,'reject_frame')
    a.imm(9,0xEF1E);a.call('crc7');a.can_byte(5,0xEF25);a.cmpreg(4,5);a.branch(3,'reject_crc')
    a.can_byte(4,0xEF1E);a.cmp(4,0xA4);a.branch(3,'reject_frame')
    a.can_byte(4,0xEF1F);a.cmp(4,2);a.branch(14,'reject_frame')
    a.cmp(4,0);a.branch(2,'cancel_request')
    a.can_byte(4,0xEF21);a.cmp(4,1);a.branch(8,'reject_range');a.cmp(4,64);a.branch(14,'reject_range')
    a.can_byte(4,0xEF22);a.cmp(4,1);a.branch(8,'reject_range');a.cmp(4,30);a.branch(14,'reject_range')
    a.can_byte(6,0xEF23);a.can_byte(7,0xEF24);a.shift(7,8,True);a.either(6,7);a.cmp(6,0);a.branch(2,'reject_range')
    a.call('clock');a.cmp(12,0);a.branch(2,'reject_gate');a.call('gate');a.cmp(4,0);a.branch(2,'reject_gate')
    a.can_byte(4,0xEF1F);a.cmp(4,1);a.branch(2,'start_request')
    a.ld(4,MODE);a.cmp(4,1);a.branch(3,'reject_state')
    a.can_byte(6,0xEF23);a.can_byte(7,0xEF24);a.shift(7,8,True);a.either(6,7)
    a.ld(5,TOKEN);a.cmpreg(6,5);a.branch(3,'reject_state')
    a.can_byte(4,0xEF20);a.ld(5,SEQ);a.sub(4,5);a.andi(4,255)
    a.cmp(4,1);a.branch(8,'reject_seq');a.cmp(4,4);a.branch(14,'reject_seq')
    a.can_byte(4,0xEF21);a.ld(5,RED);a.cmpreg(4,5);a.branch(3,'reject_range')
    a.call('wire_duration');a.ld(5,ORIGINAL_DURATION);a.cmpreg(4,5);a.branch(3,'reject_range')
    # Refresh cannot revive an expired lease or pulse, even during recovery.
    a.ld(6,RX_LO);a.ld(7,RX_HI);a.call('age');a.cmp(4,LEASE);a.branch(9,'reject_state')
    a.ld(6,START_LO);a.ld(7,START_HI);a.call('age');a.ld(5,DURATION);a.cmpreg(4,5);a.branch(9,'reject_state')
    a.branch(0,'publish_refresh')
    a.label('start_request')
    a.ld(4,TOKEN);a.addi(4,1);a.cmp(4,0);a.branch(3,'next_token_nonzero');a.imm(4,1)
    a.label('next_token_nonzero');a.cmpreg(4,6);a.branch(3,'reject_seq')
    a.ld(4,TOKEN);a.cmp(4,0);a.branch(2,'new_pulse')
    a.ld(6,START_LO);a.ld(7,START_HI);a.call('age')
    a.ld(5,ORIGINAL_DURATION);a.addi(5,COOLDOWN);a.cmpreg(4,5);a.branch(8,'reject_state')
    a.label('new_pulse')
    a.zero(MODE);a.zero(SEEN);a.zero(BEFORE);a.zero(AFTER);a.zero(START_CALL_AGE)
    a.st(START_LO,10);a.st(START_HI,11)
    a.can_byte(6,0xEF23);a.can_byte(7,0xEF24);a.shift(7,8,True);a.either(6,7);a.st(TOKEN,6)
    a.can_byte(4,0xEF21);a.st(RED,4);a.call('wire_duration');a.st(DURATION,4);a.st(ORIGINAL_DURATION,4)
    a.label('publish_refresh')
    # Atomic publication marker: readers verify EPOCH and MODE again before use.
    a.zero(MODE);a.zero(CALL_AGE);a.st(RX_LO,10);a.st(RX_HI,11);a.can_byte(4,0xEF20);a.st(SEQ,4)
    a.ld(4,EPOCH);a.addi(4,1);a.st(EPOCH,4);a.zero(REASON);a.set(MODE,1);a.zero(DIV)
    a.branch(0,'tick_owned')
    a.label('cancel_request')
    # Cancellation is idempotent, and never refreshes the lease. Require its
    # own canonical shape, but permit cancellation without knowing the token.
    for addr in (0xEF21,0xEF22):
        a.can_byte(4,addr);a.cmp(4,0);a.branch(3,'reject_range')
    a.ld(4,MODE);a.cmp(4,1);a.branch(3,'cancel_done')
    a.call('clock');a.cmp(12,0);a.branch(2,'cancel_hard')
    a.ld(6,START_LO);a.ld(7,START_HI);a.call('age');a.ld(5,DURATION)
    a.cmpreg(4,5);a.branch(9,'cancel_done')
    a.zero(MODE);a.st(DURATION,4);a.ld(4,EPOCH);a.addi(4,1);a.st(EPOCH,4);a.set(MODE,2)
    a.branch(0,'cancel_done')
    a.label('cancel_hard');a.zero(MODE)
    a.label('cancel_done');a.can_byte(4,0xEF20);a.st(SEQ,4);a.set(REASON,8);a.zero(DIV);a.branch(0,'tick_owned')
    for label,reason in [('reject_frame',1),('reject_crc',2),('reject_range',3),('reject_seq',4),('reject_state',5),('reject_gate',6)]:
        a.label(label);a.set(REASON,reason);a.zero(DIV)
        if label=='reject_frame':
            # Clear latched MsgLst and restore the receive object's canonical
            # arbitration/control. Discard this ambiguous frame; next RX works.
            a.zero(0xEF18);a.set(0xEF1A,0x8000|(0x5E8<<2));a.set(0xEF1C,0x1088)
            a.set(0xEF12,0xB0);a.set(0xEF10,11)
        a.branch(0,'tick_owned')
    a.label('status_tick')
    a.ld(4,DIV);a.cmp(4,0);a.branch(2,'status_due');a.subi(4,1);a.st(DIV,4);a.imm(4,0);a.rets()
    a.label('status_due')
    a.ld(4,0xEF80);a.andi(4,1<<11);a.branch(3,'tick_free')
    a.call('factor');a.rr(8,4);a.rr(7,5)
    a.ld(4,SEEN);a.andi(4,7);a.shift(4,4,True);a.either(7,4)
    a.shift(7,8,True);a.ori(7,0xA4);a.st(0xEF1E,7)
    a.ld(4,SEQ);a.andi(4,255);a.shift(8,8,True);a.either(4,8);a.st(0xEF20,4)
    a.ld(4,TOKEN);a.st(0xEF22,4);a.ld(4,REASON);a.andi(4,255);a.st(0xEF24,4)
    a.imm(9,0xEF1E);a.call('crc7');a.shift(4,8,True);a.ld(5,0xEF24);a.either(4,5);a.st(0xEF24,4)
    a.set(0xEF1C,0x8088);a.set(0xEF12,0x97);a.set(0xEF10,12);a.set(DIV,9);a.set(GAP,1)
    a.label('tick_owned');a.imm(4,1);a.rets()
    a.label('tick_free');a.imm(4,0);a.rets()

    a.label('wire_duration')
    a.can_byte(4,0xEF22);a.rr(5,4);a.shift(4,9,True);a.shift(5,8,True);a.add(4,5)
    a.can_byte(5,0xEF22);a.shift(5,3,True);a.add(4,5)
    a.can_byte(5,0xEF22);a.shift(5,2,True);a.add(4,5);a.can_byte(5,0xEF22);a.add(4,5);a.ret()
    a.label('clock')
    a.ld(12,0xFF44);a.andi(12,0x1FF);a.cmp(12,0x46);a.branch(3,'clock_bad')
    # Application T4 vector 0x90 -> 0x018C60 increments E176; native
    # application clock 0x018BFC reads E176. E10E is the boot-only clock,
    # reused by the running OS as configuration data. Bounded snapshot;
    # changed high half => fail this invocation, never spin in engine task.
    a.ld(11,0xE176);a.ld(10,0xFE44);a.ld(12,0xFF64);a.andi(12,0x80)
    a.ld(13,0xE176);a.cmpreg(11,13);a.branch(3,'clock_bad')
    a.cmp(12,0);a.branch(2,'clock_ok');a.cmp(10,0x8000);a.branch(9,'clock_ok');a.addi(11,1)
    a.label('clock_ok');a.imm(12,1);a.ret()
    a.label('clock_bad');a.imm(12,0);a.ret()
    a.label('age')
    a.rr(4,10);a.sub(4,6);a.rr(5,11);a.sub(5,7)
    a.cmp(5,0);a.branch(3,'age_wrap');a.cmpreg(10,6);a.branch(8,'age_old');a.ret()
    a.label('age_wrap');a.cmp(5,1);a.branch(3,'age_old');a.cmpreg(10,6);a.branch(9,'age_old');a.ret()
    a.label('age_old');a.imm(4,0xFFFF);a.ret()
    a.label('gate')
    a.ld(4,0xEF54);a.cmp(4,0x5246);a.branch(3,'gate_bad')
    a.ld(4,0xEF4E);a.andi(4,255);a.branch(3,'gate_bad')
    a.ld(4,0xEF00);a.andi(4,1);a.branch(3,'gate_bad')
    a.ld(4,0xEF02);a.andi(4,0x80);a.branch(3,'gate_bad')
    a.physical(4,0xF7C4);a.cmp(4,4800);a.branch(8,'gate_bad');a.cmp(4,26000);a.branch(14,'gate_bad')
    a.imm(4,1);a.ret()
    a.label('gate_bad');a.imm(4,0);a.ret()
    a.label('factor')
    a.ld(4,MAGIC);a.cmp(4,TAG);a.branch(3,'factor_idle')
    a.ld(4,MODE);a.cmp(4,0);a.branch(2,'factor_idle');a.cmp(4,2);a.branch(14,'factor_fault')
    a.ld(15,EPOCH)
    a.ld(4,CALL_AGE);a.cmp(4,100);a.branch(9,'factor_fault')
    a.ld(4,START_CALL_AGE);a.cmp(4,250);a.branch(9,'factor_fault')
    a.call('clock');a.cmp(12,0);a.branch(2,'factor_fault')
    a.call('gate');a.cmp(4,0);a.branch(2,'factor_fault')
    a.ld(6,START_LO);a.ld(7,START_HI);a.call('age');a.rr(8,4)
    a.ld(6,RX_LO);a.ld(7,RX_HI);a.call('age');a.rr(9,4)
    a.ld(6,RED);a.cmp(6,64);a.branch(14,'factor_fault')
    a.ld(7,DURATION);a.cmp(7,PULSE_MAX);a.branch(14,'factor_fault')
    a.imm(13,0);a.cmpreg(8,7);a.branch(8,'lease_check');a.rr(13,8);a.sub(13,7)
    a.label('lease_check');a.cmp(9,LEASE);a.branch(8,'overdue_done');a.subi(9,LEASE)
    a.cmpreg(9,13);a.branch(8,'overdue_done');a.rr(13,9)
    a.label('overdue_done')
    a.rr(4,8);a.sub(4,13);a.shift(4,5);a.cmpreg(4,6);a.branch(8,'rise_value');a.rr(4,6)
    a.label('rise_value');a.imm(5,1);a.cmpreg(4,6);a.branch(3,'release_value');a.imm(5,2)
    a.label('release_value');a.cmp(13,0);a.branch(2,'factor_check');a.imm(5,3);a.shift(13,7)
    a.cmpreg(4,13);a.branch(15,'factor_expired');a.sub(4,13);a.branch(0,'factor_check')
    # End the old request once its ramp has reached zero. Check the publication
    # epoch and clear MODE in one four-instruction ATOMIC sequence (PM0036).
    # A concurrently published new request must never be cleared by this reader.
    a.label('factor_expired');a.raw('d130','ATOMIC #4')
    a.ld(6,EPOCH);a.cmpreg(6,15);a.branch(3,'factor_idle');a.zero(MODE)
    a.imm(4,0);a.imm(5,4);a.ret()
    a.label('factor_check')
    a.ld(6,EPOCH);a.cmpreg(6,15);a.branch(3,'factor_idle');a.ld(6,MODE);a.cmp(6,0);a.branch(2,'factor_idle');a.ret()
    a.label('factor_fault');a.zero(MODE);a.set(REASON,6);a.imm(4,0);a.imm(5,5);a.ret()
    a.label('factor_idle');a.imm(4,0);a.imm(5,0);a.ret()

    # CRC-8/SAE-J1850 parameters, seven payload bytes; distinct magic/IDs.
    a.label('crc7');a.imm(4,255)
    for i in range(7):
        # R9 points at the aligned CAN IF1 data window; never use MOVB here.
        a.indexed(5,9,i&~1,3)
        if i&1:a.shift(5,8)
        else:a.andi(5,255)
        a.xor(4,5)
        for j in range(8):
            a.rr(6,4);a.andi(6,128);a.shift(4,1,True);a.cmp(6,0);a.branch(2,f'crc_{i}_{j}')
            a.xor_i(4,0x1D);a.label(f'crc_{i}_{j}');a.andi(4,255)
    a.xor_i(4,255);a.ret()
    # Input R13=u16 native request, R14=Q8 reduction; exact floor(x*(256-r)/256).
    # Avoid MDL/MDH and the multiplier shared with native interrupt handlers.
    a.label('scale');a.rr(6,13);a.shift(6,8);a.rr(7,13);a.andi(7,255);a.rr(8,14)
    a.imm(4,0);a.imm(5,0)
    for i in range(7):
        a.rr(9,8);a.andi(9,1);a.branch(2,f'mul_next_{i}');a.add(4,6);a.add(5,7)
        a.label(f'mul_next_{i}');a.shift(6,1,True);a.shift(7,1,True);a.shift(8,1)
    a.addi(5,255);a.shift(5,8);a.add(4,5);a.rr(5,13);a.sub(5,4);a.rr(4,5);a.ret()
    for name,target,path in [('hook_air',9,1),('hook_fast',7,2),('hook_load',9,4)]:
        a.label(name);a.raw('ec88','PUSH PSW')
        saved=[r for r in range(4,16) if r!=target]
        for r in saved:a.push(r)
        a.push(target);a.call('factor');a.pop(target)
        a.cmp(4,0);a.branch(2,name+'_restore')
        a.rr(14,4);a.rr(13,target);a.call('scale');a.st(BEFORE,13);a.st(AFTER,4);a.rr(target,4)
        # Only this observation marks a native hook as reached. RX acceptance
        # and status construction never claim native execution.
        a.raw('d120','ATOMIC #3');a.ld(4,SEEN);a.ori(4,path);a.st(SEEN,4)
        a.label(name+'_restore')
        for r in reversed(saved):a.pop(r)
        a.raw('fc88','POP PSW')
        if name=='hook_air':a.raw('42f97c97','CMP R9,977Ch ; displaced OEM instruction')
        elif name=='hook_fast':a.raw('f08742f75e97','MOV R8,R7; CMP R7,975Eh ; displaced OEM instructions')
        else:a.raw('f2f47c97','MOV R4,977Ch ; displaced OEM instruction')
        a.rets()
    return a,a.finish()
