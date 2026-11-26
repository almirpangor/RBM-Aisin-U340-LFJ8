"""Small fail-closed interpreter for tested functions in the byte-checked listing.
Implements a subset of V850E1 instruction semantics, not peripherals or a full ECU.
Instructions and addresses come from the original listing, not the lifted C.
Unknown instructions, reads and division by zero are errors.
"""
from pathlib import Path
import re
MASK=0xffffffff
GP=0x03ff4000
REGS={'gp':4,'sp':3,'lp':31,'ep':30}
def sx(v,n=32):
    v&=(1<<n)-1
    return v-(1<<n) if v&(1<<(n-1)) else v
class V850:
    def __init__(self,rom,listing):
        self.rom=rom; self.code={}; self.raw={}
        for line in listing.splitlines():
            m=re.match(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(\S+)?\s*(.*)',line)
            if not m: continue
            a=int(m[1],16);raw=bytes.fromhex(m[2])
            assert rom[a:a+len(raw)]==raw,(hex(a),'bytes')
            if m[3]: self.code[a]=(m[3],m[4].strip(),a+len(raw))
        # GNU objdump wraps 6-byte MOV immediate after the first four bytes.
        for a,(op,arg,nxt) in list(self.code.items()):
            if op=='mov' and a+4 not in self.code and a+6 in self.code and nxt==a+4:
                self.code[a]=(op,arg,a+6)
        self.reset()
    def reset(self):
        self.r=[0]*32;self.r[3]=0x04008000;self.r[4]=GP;self.r[5]=0xa740;self.r[31]=MASK
        self.ram={};self.frames=[];self.z=self.s=self.cy=self.ov=False
        self.interrupts_disabled=False
    def reg(self,s): return REGS[s] if s in REGS else int(s[1:])
    def val(self,s): return self.r[self.reg(s)] if s in REGS or re.fullmatch(r'r\d+',s) else int(s,0)
    def put(self,s,v):
        i=self.reg(s)
        if i:self.r[i]=v&MASK
    def address(self,s):
        m=re.fullmatch(r'(-?\d+)\[(\w+)\]',s)
        if not m: raise ValueError(s)
        return (int(m[1])+self.val(m[2]))&MASK
    def read(self,a,n):
        if a+n<=len(self.rom): return int.from_bytes(self.rom[a:a+n],'little')
        return sum(self.ram[a+i]<<(8*i) for i in range(n))
    def write(self,a,n,v):
        assert a>=len(self.rom),'ROM write'
        for i in range(n):self.ram[a+i]=(v>>(8*i))&255
    def alu(self,a,b,subtract=False):
        a&=MASK;b&=MASK
        full=b-a if subtract else b+a;r=full&MASK
        self.z=r==0;self.s=bool(r&0x80000000)
        self.cy=b<a if subtract else full>MASK
        self.ov=bool(((a^b)&(b^r) if subtract else ~(a^b)&(b^r))&0x80000000)
        return r
    def bitflags(self,r):
        self.z=(r&MASK)==0;self.s=bool(r&0x80000000);self.ov=False
    def cond(self,op):
        return {'br':True,'be':self.z,'bne':not self.z,'bl':self.cy,'bnl':not self.cy,
            'bnh':self.cy or self.z,'bh':not self.cy and not self.z,
            'blt':self.s!=self.ov,'bge':self.s==self.ov,
            'ble':self.z or self.s!=self.ov,'bgt':not self.z and self.s==self.ov,
            'bp':not self.s,'bn':self.s,'bv':self.ov,'bnv':not self.ov}[op]
    def saved(self,arg):
        body=arg.split('{')[1].split('}')[0];items=[]
        for item in body.split(','):
            item=item.strip()
            if ' - ' in item:
                a,b=item.split(' - ');items.extend(range(self.reg(a),self.reg(b)+1))
            else: items.append(self.reg(item))
        return items
    def run(self,entry,limit=10000,stop=None,hooks=None,coverage=None):
        pc=entry;steps=0
        while pc!=MASK and pc!=stop:
            steps+=1
            if steps>limit:raise RuntimeError(('step limit',hex(pc)))
            if coverage is not None:coverage.add(pc)
            op,arg,nxt=self.code[pc];a=[s.strip() for s in arg.split(',')]
            try:
                if op=='mov': self.put(a[1],self.val(a[0]))
                elif op in ('movea','addi','movhi'):
                    v=self.val(a[0]);v=v<<16 if op=='movhi' else v
                    self.put(a[2],self.alu(v,self.val(a[1])) if op=='addi' else self.val(a[1])+v)
                elif op in ('add','sub','subr','cmp'):
                    x,y=self.val(a[0]),self.val(a[1])
                    r=self.alu(y,x,True) if op=='subr' else self.alu(x,y,op!='add')
                    if op!='cmp':self.put(a[1],r)
                elif op in ('andi','ori','xori'):
                    x,y=self.val(a[0]),self.val(a[1]);r=x&y if op=='andi' else x|y if op=='ori' else x^y
                    self.put(a[2],r);self.bitflags(r)
                elif op in ('and','or','xor'):
                    x,y=self.val(a[0]),self.val(a[1])
                    r=x&y if op=='and' else x|y if op=='or' else x^y
                    self.put(a[1],r);self.bitflags(r)
                elif op in ('satadd','satsub'):
                    x,y=self.val(a[0]),self.val(a[1])
                    self.alu(x,y,op=='satsub')
                    full=sx(y)-sx(x) if op=='satsub' else sx(y)+sx(x)
                    r=max(-2147483648,min(2147483647,full))
                    self.put(a[1],r);self.z=r==0;self.s=r<0
                elif op in ('shl','shr','sar'):
                    n=self.val(a[0])&31;v=self.val(a[1])
                    r=(v<<n)&MASK if op=='shl' else v>>n if op=='shr' else sx(v)>>n
                    if n:self.cy=bool((v>>(32-n if op=='shl' else n-1))&1)
                    self.put(a[1],r);self.bitflags(r)
                elif op in ('zxb','zxh','sxb','sxh'):
                    n=8 if op.endswith('b') else 16;v=self.val(a[0])
                    self.put(a[0],sx(v,n) if op.startswith('s') else v&((1<<n)-1))
                elif op in ('mulhi','mulh'):
                    self.put(a[-1],sx(self.val(a[0]),16)*sx(self.val(a[1]),16))
                elif op in ('mulu','mul'):
                    x,y=self.val(a[0]),self.val(a[1])
                    p=x*y if op=='mulu' else sx(x)*sx(y)
                    self.put(a[1],p);self.put(a[2],p>>32)
                elif op=='divhu':
                    d=self.val(a[0])&65535;v=self.val(a[1]);q,r=divmod(v,d)
                    self.put(a[1],q);self.put(a[2],r)
                elif op=='divh':
                    d=sx(self.val(a[0]),16);v=sx(self.val(a[1]))
                    if not d:raise ZeroDivisionError('undefined DIVH quotient')
                    q=abs(v)//abs(d);q=-q if (v<0)!=(d<0) else q
                    self.ov=not(-2147483648<=q<=2147483647)
                    self.put(a[1],q);self.z=(q&MASK)==0;self.s=sx(q)<0
                    if len(a)==3:self.put(a[2],v-q*d)
                elif op=='cmov':
                    cond={'h':'bh','z':'be','nz':'bne','lt':'blt','ge':'bge','le':'ble','gt':'bgt'}[a[0]]
                    self.put(a[3],self.val(a[1]) if self.cond(cond) else self.val(a[2]))
                elif op=='setf':
                    cond={'h':'bh','z':'be','nz':'bne','lt':'blt','ge':'bge','le':'ble','gt':'bgt'}[a[0]]
                    self.put(a[1],int(self.cond(cond)))
                elif op.startswith('ld.'):
                    n={'ld.b':1,'ld.bu':1,'ld.h':2,'ld.hu':2,'ld.w':4}[op]
                    v=self.read(self.address(a[0]),n)
                    self.put(a[1],sx(v,n*8) if op in ('ld.b','ld.h') else v)
                elif op=='sld.w':self.put(a[1],self.read(self.address(a[0]),4))
                elif op=='sld.hu':self.put(a[1],self.read(self.address(a[0]),2))
                elif op=='sst.w':self.write(self.address(a[1]),4,self.val(a[0]))
                elif op=='sst.h':self.write(self.address(a[1]),2,self.val(a[0]))
                elif op=='sst.b':self.write(self.address(a[1]),1,self.val(a[0]))
                elif op.startswith('st.'):
                    n={'st.b':1,'st.h':2,'st.w':4}[op]
                    self.write(self.address(a[1]),n,self.val(a[0]))
                elif op in ('tst1','set1','clr1'):
                    addr=self.address(a[1]);v=self.read(addr,1);mask=1<<int(a[0]);self.z=not(v&mask)
                    if op!='tst1':self.write(addr,1,v|mask if op=='set1' else v&~mask)
                elif op=='prepare':
                    # GNU listing prints encoded imm5, in words. Save ascending,
                    # restore descending. Keep stack locals in actual VM RAM.
                    regs=sorted(self.saved(arg));tail=arg.split('}',1)[1].strip(', ')
                    operands=[x.strip() for x in tail.split(',')]
                    for i in regs:
                        self.r[3]=(self.r[3]-4)&MASK
                        self.write(self.r[3]&~3,4,self.r[i])
                    self.r[3]=(self.r[3]-4*int(operands[0],0))&MASK
                    if len(operands)>1:self.r[30]=self.val(operands[1])&MASK
                elif op=='dispose':
                    self.r[3]=(self.r[3]+4*int(a[0],0))&MASK
                    for i in sorted(self.saved(arg),reverse=True):
                        self.r[i]=self.read(self.r[3]&~3,4)
                        self.r[3]=(self.r[3]+4)&MASK
                    tail=arg.split('}',1)[1].strip(', ')
                    if tail:nxt=self.val(tail.strip('[]'))
                elif op=='jarl':
                    self.put(a[1],nxt)
                    target=int(a[0],0)
                    if hooks and target in hooks: hooks[target](self)
                    else: nxt=target
                elif op=='jmp':nxt=self.val(arg.strip('[]'))
                elif op=='jr':nxt=int(arg,0)
                elif op=='switch':
                    # Renesas SWITCH: target relative to table start, signed halfword.
                    base=pc+2
                    nxt=(base+2*sx(self.read((base+2*self.val(arg))&MASK,2),16))&MASK
                elif op=='di':self.interrupts_disabled=True
                elif op=='ei':self.interrupts_disabled=False
                elif op.startswith('b'):
                    if self.cond(op):nxt=int(arg,0)
                elif op=='nop':pass
                else:raise NotImplementedError(op)
            except Exception as e:raise RuntimeError(f'{pc:06x}: {op} {arg}: {e}') from e
            pc=nxt
        return self.r[10]

