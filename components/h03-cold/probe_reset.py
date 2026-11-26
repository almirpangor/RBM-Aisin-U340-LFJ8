from pathlib import Path
import sys, json, re, hashlib
sys.path.insert(0,str(Path(__file__).parent))
import v850_subset

rom=Path('s01.bin').read_bytes()
listing=Path('s01-listing.txt').read_text()
vm=v850_subset.V850(rom,listing)
vm.ram.update({a:(a*73+0x55)&255 for a in range(0x3ff0000,0x3ff8000)})
cover=set()
vm.run(0x12d64,stop=0x12dbc,limit=30000,coverage=cover)
assert all(vm.ram[a]==0 for a in range(0x3ff18f0,0x3ff69f4))
print('BSS PASS',len(cover),len(range(0x3ff18f0,0x3ff69f4)))
vm.ram[v850_subset.GP-5274]=1
vm.ram[v850_subset.GP-1422]=0
vm.ram[v850_subset.GP-10004]=0x55
vm.ram[v850_subset.GP-10003]=0xaa
vm.r[31]=0xffffffff
vm.interrupts_disabled=True
def psw(v): v.r[10]=32 if v.interrupts_disabled else 0
vm.run(0x540b0,limit=50000,hooks={0x1accc:psw},coverage=cover)
print('COLD PASS',len(cover))
Path('reset-cold-ram.json').write_text(json.dumps({str(a-v850_subset.GP):v for a,v in vm.ram.items() if -10000<=a-v850_subset.GP<10740},indent=2))
