"""Bounded frozen comparison; gold fixture fields never enter model payloads."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from epistemic_harness.client import Client
from epistemic_harness.pipeline import run_case
from epistemic_harness.environment import load_env_file


def frozen():
    entries=json.loads((ROOT/'validation/freeze.json').read_text())['sha256']
    for name,h in entries.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:
            raise ValueError('Frozen file changed: '+name)


def rows(name):
    return [json.loads(x) for x in (ROOT/name).read_text().splitlines() if x.strip()]


def clean(case):
    return {k:v for k,v in case.items() if k not in (
        'fixed_candidate','gold_support','gold_coverage','label_provenance','pair_id','split')}


def write_run(name,cases,config,replays=None):
    path=ROOT/'runs'/f'{name}.jsonl'
    if path.exists():raise ValueError('Existing log preserved: '+path.name)
    client=Client(config);rid=str(uuid.uuid4());records=[]
    with path.open('w') as log:
        for case in cases:
            r=run_case(case,client,config['verification_mode'],replay=(replays or {}).get(case['id']))
            r.update(run_id=rid,config=client.public_settings(),timestamp=datetime.now(timezone.utc).isoformat())
            log.write(json.dumps(r,allow_nan=False)+'\n');log.flush();records.append(r)
            print(f'{name} {case["id"]}: {r["status"]}, emitted {bool(r["rewrite_plan"])}',flush=True)
    return records


def compare(name,fixtures):
    cases=[clean(r) for r in fixtures]
    replay={r['id']:{'case_id':r['id'],'question':r['question'],'candidate':r['fixed_candidate'],
        'claims':[{'text':r['fixed_candidate']}],'run_id':'frozen-stage3-fixture'} for r in fixtures}
    for arm,file in [('baseline','config.baseline.json'),('alignment','config.json')]:
        write_run(f'{name}-{arm}',cases,json.loads((ROOT/file).read_text()),replay)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['evidence','arithmetic','fresh'],required=True)
    parser.add_argument('--env-file',type=Path,default=ROOT.parent/'epistemic-harness/.env');args=parser.parse_args()
    frozen();load_env_file(args.env_file)
    if args.phase=='evidence':compare('evidence',rows('benchmarks/evidence-pairs.jsonl'))
    elif args.phase=='arithmetic':compare('arithmetic',rows('benchmarks/arithmetic-coverage.jsonl'))
    else:
        cases=rows('benchmarks/fresh-tasks.jsonl')
        cfg=json.loads((ROOT/'config.baseline.json').read_text());cfg.update(verification_mode='benchmark',task_completion='off')
        generated=write_run('fresh-generation',cases,cfg)
        replay={r['case_id']:{'case_id':r['case_id'],'question':r['question'],'candidate':r['candidate'],
            'claims':[{'text':r['candidate']}],'run_id':r['run_id']} for r in generated if r['status']=='ok'}
        if len(replay)!=len(cases):raise ValueError('Generation failed; do not invent replacement candidates')
        (ROOT/'validation/fresh-generation-sha256.txt').write_text(hashlib.sha256((ROOT/'runs/fresh-generation.jsonl').read_bytes()).hexdigest()+'\n')
        for arm,file in [('baseline','config.baseline.json'),('alignment','config.json')]:
            write_run(f'fresh-{arm}',cases,json.loads((ROOT/file).read_text()),replay)
    frozen()

if __name__=='__main__':main()
