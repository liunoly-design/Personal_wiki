"""Build the pinned official whisper.cpp server; model weights supplied separately."""
import argparse,json,subprocess
from pathlib import Path
REVISION='60c0be6ac8fa71b1a2ae2dd938a31a34a508e774'
p=argparse.ArgumentParser();p.add_argument('--destination',required=True);a=p.parse_args();target=Path(a.destination)
if not target.is_absolute() or target.exists():raise SystemExit('An empty absolute destination is required')
subprocess.run(['git','clone','https://github.com/ggml-org/whisper.cpp.git',str(target)],check=True)
subprocess.run(['git','checkout','--detach',REVISION],cwd=target,check=True)
subprocess.run(['cmake','-S',str(target),'-B',str(target/'build'),'-DWHISPER_BUILD_SERVER=ON','-DCMAKE_BUILD_TYPE=Release'],check=True)
subprocess.run(['cmake','--build',str(target/'build'),'--config','Release','-j','2','--target','whisper-server'],check=True)
print(json.dumps({'revision':REVISION,'binary':str(target/'build/bin/whisper-server')}))
