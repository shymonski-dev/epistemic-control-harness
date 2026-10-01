"""Offline results reconstruction with both pre-inference freezes checked."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from epistemic_harness.metrics import summarize


def read(path):
    return [json.loads(x) for x in (ROOT/path).read_text().splitlines() if x.strip()]


def emitted(r):
    return any(p['certainty']!='abstain' for p in r['rewrite_plan'])


def assess(records,labels):
    eligible={k for k,v in labels.items() if v['support']=='supported' and v['coverage']=='complete'}
    support=lambda r:r['decisions'][0]['verification']['status'] if r['decisions'] else 'error'
    return {'eligible_supported_complete':len(eligible),
        'useful_emitted':sum(emitted(r) and r['case_id'] in eligible for r in records),
        'supported_complete_withheld':[r['case_id'] for r in records if not emitted(r) and r['case_id'] in eligible],
        'unsupported_emitted':[r['case_id'] for r in records if emitted(r) and labels[r['case_id']]['support']!='supported'],
        'incomplete_emitted':[r['case_id'] for r in records if emitted(r) and labels[r['case_id']]['coverage']!='complete'],
        'unjustified_supported_verdicts':[r['case_id'] for r in records if support(r)=='supported' and labels[r['case_id']]['support']!='supported'],
        'incorrect_contradictions':[r['case_id'] for r in records if support(r)=='contradicted' and labels[r['case_id']]['support']!='contradicted'],
        'verdict_label_matches':sum(support(r)==labels[r['case_id']]['support'] for r in records),
        'audit_pass_count':sum(r['audit']['passed'] for r in records),
        'metrics':summarize(records)}


def main():
    for name in ['freeze.json','task-freeze.json']:
        for f,h in json.loads((ROOT/'validation'/name).read_text())['sha256'].items():
            assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,'Frozen file changed: '+f
    generated=ROOT/'runs/fresh-generation.jsonl'
    if generated.exists():
        assert hashlib.sha256(generated.read_bytes()).hexdigest()==(ROOT/'validation/fresh-generation-sha256.txt').read_text().strip()
    cases=read('benchmarks/evidence-pairs.jsonl')
    labels={r['id']:{'support':r['gold_support'],'coverage':r['gold_coverage']} for r in cases}
    result={}
    for split in ['development','holdout']:
        ids={r['id'] for r in cases if r['split']==split}
        result[split]={arm:assess([r for r in read(f'runs/evidence-{arm}.jsonl') if r['case_id'] in ids],
                                     {k:v for k,v in labels.items() if k in ids}) for arm in ['baseline','alignment']}
    cases=read('benchmarks/arithmetic-coverage.jsonl')
    labels={r['id']:{'support':r['gold_support'],'coverage':r['gold_coverage']} for r in cases}
    result['arithmetic']={arm:assess(read(f'runs/arithmetic-{arm}.jsonl'),labels) for arm in ['baseline','alignment']}
    review=ROOT/'validation/fresh-review.json'
    if review.exists():
        labels={r['case_id']:r for r in json.loads(review.read_text())['cases']}
        result['fresh']={arm:assess(read(f'runs/fresh-{arm}.jsonl'),labels) for arm in ['baseline','alignment']}
    holdout=result['holdout'];proposal=holdout['alignment'];baseline=holdout['baseline']
    result['heldout_adoption_conditions_met']=(not proposal['unsupported_emitted'] and
        proposal['useful_emitted']>=baseline['useful_emitted'] and proposal['metrics']['error_count']==0 and
        proposal['metrics']['overstatement_rate']==0)
    result['promotion_decision']='Experimental: heldout emission conditions alone are insufficient; development has a mapping failure and retention loss, with residual incorrect contradiction and an ambiguous fresh inference.'
    result['provenance']='Two boundary labels confirmed by user; other fixture labels assistant-authored before inference. Fresh review after inference is separate. Same-model double review is correlated; small heldout set is not an independent research benchmark.'
    (ROOT/'validation/results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
