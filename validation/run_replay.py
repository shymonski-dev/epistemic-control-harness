"""24 Jev requests maximum; mapping and completion are frozen, never regenerated."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from epistemic_harness.client import Client
from epistemic_harness.environment import load_env_file
from epistemic_harness.pipeline import run_case


def check_freeze():
    for p,h in json.loads((ROOT/'validation/release-freeze.json').read_text())['sha256'].items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('Frozen file changed: '+p)


def rows(name):
    return [json.loads(x) for x in (ROOT/name).read_text().splitlines() if x.strip()]


class Budget:
    calls=0
    cost=0.0
    tokens=0
    unknown_usage=False


class FrozenClient(Client):
    def __init__(self,config,source,budget):
        super().__init__(config);self.source=source;self.budget=budget
    def complete(self,role,system,payload,*,response_format=None):
        name=response_format['json_schema']['name']
        if role!='verifier':raise ValueError('Replay cannot generate new text')
        if name=='evidence_map':
            v=self.source['first_verdict']
            return json.dumps({'score':v['score'],'parts':[{k:p[k] for k in ('text','status','evidence_quote','reason')}
                for p in v['evidence_check']['parts']]})
        if name=='requirement_coverage':
            c=self.source['completion']
            if 'checks' not in c:raise ValueError('No frozen completion checks for a selected answer')
            return json.dumps({'checks':[{k:p[k] for k in ('requirement_id','status','evidence','reason')} for p in c['checks']]})
        raise ValueError('Replay cannot make a new chat call')
    def decide(self,state,questions):
        budget=self.budget
        if budget.calls>=24 or budget.cost>=.02 or budget.tokens>=40000 or budget.unknown_usage:
            raise RuntimeError('Bounded Jev replay budget exhausted')
        budget.calls+=1
        response=super().decide(state,questions)
        usage=response['usage']
        if 'cost' not in usage or 'input_tokens' not in usage:budget.unknown_usage=True
        budget.cost+=usage.get('cost',0);budget.tokens+=usage.get('input_tokens',0)
        return response


def main():
    check_freeze()
    files=[ROOT/'runs/replay-baseline.jsonl',ROOT/'runs/replay-jev.jsonl']
    if any(p.exists() for p in files):raise ValueError('Existing evaluation logs preserved')
    load_env_file(ROOT.parent/'epistemic-harness/.env')
    sources={r['case_id']:r for r in rows('validation/frozen-replay.jsonl')}
    fixtures=rows('benchmarks/evidence-pairs.jsonl')
    cases=[{k:v for k,v in r.items() if k not in ('fixed_candidate','gold_support','gold_coverage','label_provenance','pair_id','split')} for r in fixtures]
    budget=Budget()
    for arm,filename in [('baseline','config.json'),('jev','config.jev.json')]:
        config=json.loads((ROOT/filename).read_text())
        if arm=='baseline':config['verification_protocol']='evidence_map'
        rid=str(uuid.uuid4())
        with (ROOT/f'runs/replay-{arm}.jsonl').open('w') as log:
            for case in cases:
                source=sources[case['id']];client=FrozenClient(config,source,budget)
                replay={'case_id':case['id'],'question':case['question'],'candidate':source['candidate'],
                    'claims':[{'text':source['candidate']}],'run_id':source['source_run_id']}
                r=run_case(case,client,'stage2',replay=replay)
                r.update(run_id=rid,timestamp=datetime.now(timezone.utc).isoformat(),config=client.public_settings(),
                         mapping_and_completion='frozen_stage3_baseline',live_calls='Jev only' if arm=='jev' else 'none')
                if arm=='baseline':
                    assert r['status']=='ok' and r['final']==source['historical_final'] and r['rewrite_plan']==source['historical_plan']
                log.write(json.dumps(r,allow_nan=False)+'\n');log.flush()
                print(f'{arm} {case["id"]}: {r["status"]}, emitted {bool(r["rewrite_plan"])}',flush=True)
    (ROOT/'validation/usage.json').write_text(json.dumps({'requests':budget.calls,'input_tokens':budget.tokens,
        'reported_cost_usd':budget.cost,'unknown_usage':budget.unknown_usage,
        'limits':{'requests':24,'input_tokens':40000,'reported_cost_usd':.02},
        'note':'Limits stop subsequent calls once reached; the current in-flight request may cross token/cost limits. No retries or new chat calls.'},indent=2)+'\n')
    check_freeze()

if __name__=='__main__':main()
