"""Offline check that transport repairs preserve every recorded pipeline decision."""
import hashlib
import json
from pathlib import Path
from run_replay import FrozenClient, ROOT, check_freeze, rows
from epistemic_harness.pipeline import run_case


class RecordedClient(FrozenClient):
    def __init__(self, config, source, recorded):
        super().__init__(config, source, None)
        self.recorded = recorded
        self.calls = 0

    def decide(self, state, questions):
        self.calls += 1
        trace = self.recorded['decisions'][0]['verification']['evidence_check']
        reply = dict(trace['jev'])
        reply['answers'] = {f'p{i}': part['jev'] for i, part in enumerate(trace['parts'], 1)}
        # Verify that the recorded response belongs to this exact blinded request.
        body = json.dumps({'model': self.config['decision_reviewer']['model'],
                           'state': state, 'questions': questions},
                          allow_nan=False, ensure_ascii=False).encode()
        assert hashlib.sha256(body).hexdigest() == reply['request_sha256']
        return reply


def main():
    check_freeze()
    sources = {r['case_id']: r for r in rows('validation/frozen-replay.jsonl')}
    compared = calls = 0
    for arm, filename in [('baseline', 'config.json'), ('jev', 'config.jev.json')]:
        config = json.loads((ROOT / filename).read_text())
        if arm == 'baseline':
            config['verification_protocol'] = 'evidence_map'
        for recorded in rows(f'runs/replay-{arm}.jsonl'):
            source = sources[recorded['case_id']]
            client = RecordedClient(config, source, recorded)
            replay = {'case_id': source['case_id'], 'question': source['question'],
                      'candidate': source['candidate'], 'claims': [{'text': source['candidate']}],
                      'run_id': source['source_run_id']}
            actual = run_case(recorded['benchmark'], client, 'stage2', replay=replay)
            for field in ['status', 'decisions', 'rewrite_plan', 'pre_completion_plan',
                          'task_completion', 'completion_withheld', 'final', 'audit']:
                assert actual.get(field) == recorded.get(field), (arm, source['case_id'], field)
            compared += 1
            calls += client.calls
    assert compared == 48 and calls == 24
    print(json.dumps({'pipeline_records_reproduced': compared, 'recorded_jev_responses': calls,
                      'network_calls': 0, 'decisions_unchanged_after_repairs': True}))


if __name__ == '__main__':
    main()
