import json,secrets
from pathlib import Path
path=Path(__file__).with_name('.env')
values={}
for line in path.read_text(encoding='utf-8-sig').splitlines():
    key,sep,value=line.partition('=')
    if sep and not key.lstrip().startswith('#'): values[key.strip()]=value.strip()
values.setdefault('SG_QUEUE_SECRET',secrets.token_urlsafe(48))
values['SG_QUEUE_ORIGIN']='https://steamgamers-squad-roost.roostamsevbyanov.chatgpt.site'
values['SG_RUN_BOT']='1'
values['SG_ACCEPT_APPLICATIONS']='0'
path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n',encoding='utf-8')
# Consumed only by the orchestration tool, never echoed in user-visible output.
print(json.dumps({'secret':values['SG_QUEUE_SECRET']}))
