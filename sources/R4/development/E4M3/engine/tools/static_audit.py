from pathlib import Path
import hashlib,json,struct,sys
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import argparse
p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('image',type=Path);p.add_argument('report',type=Path);p.add_argument('--outdir',type=Path,required=True)
args=p.parse_args();args.outdir.mkdir(parents=True,exist_ok=True)
from c166_disasm import C166Disassembler
BASE=args.base.read_bytes()
B=args.image.read_bytes()
report=json.loads(args.report.read_text())
N=report['code_bytes'];o=0xE200
assert len(B)==len(BASE)==851968
assert all(v==0xff for v in BASE[o:o+N])
# Separate checksum implementation: parse table addresses directly; bytewise sum.
records=[]
for p in list(range(0xA7800,0xA7B00,16))+[0xA83CC,0xA83DC,0xA83EC]:
 first,last,want,inv=struct.unpack_from('<IIII',B,p)
 assert B[p:p+8]==BASE[p:p+8]
 def pos(a):
  assert 0<=a<0x8000 or 0x18000<=a<0xe0000
  return a if a<0x8000 else a-0x10000
 lo,hi=pos(first),pos(last)+1
 got=0
 for j in range(lo,hi,2):got=(got+B[j]+256*B[j+1])&0xffffffff
 assert want==got and inv==(0xffffffff-got)
 records.append({'record':f'{p:06X}','start_cpu':f'{first:06X}','end_cpu':f'{last:06X}','valid':True})
# Exact allowed footprint is defined independently from patch-report "patches".
allowed=set(range(o,o+N))|set(range(0x8405c,0x84060))
for p in (0x2fc,0x302,0x30e,0x314,0x336,0xbc38,0xbc3e):
 allowed.update([p,p+1]);assert int.from_bytes(B[p:p+2],'little')==int.from_bytes(BASE[p:p+2],'little')|1
for r in records:
 p=int(r['record'],16);allowed.update(range(p+8,p+16))
changed={i for i in range(len(B)) if B[i]!=BASE[i]}
assert not changed-allowed
assert B[0x8405c:0x84060]==bytes.fromhex('da0100e2')
assert B[o:o+4]==bytes.fromhex('da0160a0')
assert B[0x84060:0x8407a]==BASE[0x84060:0x8407a]
# Instruction boundaries and control flow independently from emitter labels.
d=C166Disassembler();rows=d.decode_range(B[o:o+N],0x1E200,N)
starts={ea for ea,h,t in rows};branches=[];stores=[];reads=[];lst=[]
for i,(ea,h,t) in enumerate(rows):
 raw=bytes.fromhex(h);op=raw[0]
 if op==0xD7:
  assert raw[:2]==bytes.fromhex('d740')
  page=int.from_bytes(raw[2:],'little');t=f'EXTP #{page:04X}h,#1 (PM0036)'
 elif op==0xC0:
  rb=raw[1]>>4;rd=raw[1]&15
  t=f'MOVBZ R{rd},R{"H" if rb&1 else "L"}{rb//2} (byte source; PM0036)'
 elif op==0xC2:
  t=f'MOVBZ R{raw[1]&15},0x{int.from_bytes(raw[2:],"little"):04X} (word destination; PM0036)'
 assert '(unknown' not in t and '(decode error' not in t
 lst.append(f'{ea:06X} file:{ea-0x10000:06X} {h:9} {t}')
 if op in (0xEA,0xCA):
  target=(ea&0xff0000)|int.from_bytes(raw[2:],'little')
  assert target in starts;branches.append(target)
 if op==0xDA:assert raw==bytes.fromhex('da0160a0')
 if op in (0xF2,0xC2,0xF6):
  addr=int.from_bytes(raw[2:],'little');prev=bytes.fromhex(rows[i-1][1])
  if prev[:2]==bytes.fromhex('d740'):addr=int.from_bytes(prev[2:],'little')*0x4000+(addr&0x3fff)
  if op==0xF6:
   assert 0xef00<=addr<=0xef54 and addr!=0xef40
   stores.append(addr)
  else:reads.append(addr)
assert rows[-1][0]+len(bytes.fromhex(rows[-1][1]))==0x1E200+N
assert bytes.fromhex(rows[-1][1])==b'\xdb\x00'
(args.outdir/'independent_disassembly_E3_SW.asm').write_text('\n'.join(lst)+'\n')
# Clock divisor decoded independently.
btr=0x6b03;brpe=0
brp=1+(btr&0x3f)+(brpe<<6);sjw=1+((btr>>6)&3);seg1=1+((btr>>8)&15);seg2=1+((btr>>12)&7)
out={'status':'PASS_STATIC_LIMITED','sha256':hashlib.sha256(B).hexdigest(),'image_bytes':len(B),'changed_bytes_vs_Rev8':len(changed),'payload_bytes':N,'decoded_instructions':len(rows),'internal_branch_targets_valid':len(branches),'known_checksum_records':len(records),'records':records,'new_code_store_addresses':sorted(set(f'{a:06X}' for a in stores)),'new_code_read_addresses':sorted(set(f'{a:06X}' for a in reads)),'outside_allowed_footprint_identical':True,'original_serial_call_preserved':True,'clock':{'BTR':hex(btr),'BRP':brp,'SJW':sjw,'TSEG1':seg1,'TSEG2':seg2,'total_tq':1+seg1+seg2,'clock_divisor':brp*(1+seg1+seg2),'sample_point_percent':100*(1+seg1)/(1+seg1+seg2),'baud_at_40MHz':40000000//(brp*(1+seg1+seg2))},'limitations':['No proof against computed references into the former FF gap','Only the 51 identified checksum records checked; no universal checksum claim','Data registers and hardware flag behavior follow ST10F276 family documentation; exact ST10F275-CEG variant still needs hardware validation','Port startup read statically; no full startup/interrupt/stack simulation']}
(args.outdir/'INDEPENDENT_STATIC_AUDIT_E3_SW.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['records','new_code_read_addresses','new_code_store_addresses']},indent=2))
