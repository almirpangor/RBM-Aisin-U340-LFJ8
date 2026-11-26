import argparse,json,os,runpy,sys,time
from pathlib import Path
root=Path.cwd();out=Path('D:/RBM-Bench-Release-Audit-20261121');temp=out/'temp'
os.environ.update(TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),PYTHONIOENCODING='utf-8')
gcc=Path('C:/Users/RBmotors/AppData/Local/Temp/rbm-m32r-smoke/gnu-m32r-elf/bin/m32r-elf-gcc.exe')
os.environ['PATH']=str(gcc.parent)+os.pathsep+os.environ.get('PATH','')
probe=runpy.run_path(str(root/'verification/project-audit/integration-11-20261121/check-composition.py'))
layout=probe['layout']
profile=out/'COMPOSITION_SIMULATOR_ONLY.h';profile.write_text(probe['PROFILE'],encoding='ascii')
args=argparse.Namespace(base=Path('D:/Новая папка (2)/Общая папка/TCM/LFJ8-T-D.bin'),gcc=gcc,
 controller=out/'controller/rbm_u340e_m32r_be.o',bridge=out/'bridge/lfj8_9e1c_m32r.o',
 storage_report=Path('D:/RBM-Integration-11-20261121/native/storage.json'),out=out/'composition',
 profile='padding-candidate',memory_model='medium',with_bindings=True,with_dtc_rx=True,
 with_dma4_guard=True,with_can_service=True,with_service_guard=True,with_ram_owner=True,
 with_application_entries=True,with_resident_constants=True,application_profile=profile,cpu_test=False,
 binding_source=[root/'targets/lfj8'/name for name in probe['PROVIDERS']])
args.out.mkdir(exist_ok=True)
try:
 report=layout.build(args)
except ValueError:
 report=json.loads((args.out/'layout.json').read_text(encoding='utf-8'))
 if report.get('status')!='FAIL_BINDINGS':raise
report.update(scope='Fresh controller and bridge; explicit native providers; simulator profile still has unresolved real inputs',hardware_verified=False,flashable_image=None)
(args.out/'composition.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report.get(k) for k in ('status','flash_payload_bytes','new_static_ram_bytes','unresolved_symbols','extra_binding_sources','known_sections_candidate_plan')},ensure_ascii=False,indent=2))

