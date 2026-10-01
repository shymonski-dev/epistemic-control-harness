"""Apply explicit, frozen review labels to a logged run; no model grading."""
import argparse
import json
from pathlib import Path


def latest_records(path: Path) -> list[dict]:
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    cases = [r for r in rows if 'case_id' in r]
    if not cases:
        raise ValueError('No case records in results')
    latest = cases[-1]['run_id']
    selected = [r for r in cases if r['run_id'] == latest]
    if len({r['case_id'] for r in selected}) != len(selected):
        raise ValueError('Duplicate case records')
    return selected


def evaluate(records: list[dict], review: dict) -> dict:
    labels = {r['case_id']: r for r in review['cases']}
    output = []
    for record in records:
        label = labels[record['case_id']]
        if record['candidate'] != label['candidate_text']:
            raise ValueError('Candidate differs from the frozen review')
        emitted = [p for p in record['rewrite_plan'] if p['certainty'] != 'abstain']
        # Whole-answer labels cannot grade arbitrary subsets of a false compound answer.
        whole_answer = len(emitted) == 1 and next(c['text'] for c in record['claims']
            if c['id'] == emitted[0]['claim_id']) == record['candidate']
        correctness = label['candidate_correct'] if whole_answer else None
        completeness = label['candidate_completeness'] if whole_answer else (
            'complete' if not emitted and label['abstention_appropriate'] else 'incomplete')
        output.append({'case_id':record['case_id'], 'candidate_correct':label['candidate_correct'],
            'candidate_completeness':label['candidate_completeness'],
            'final_factual_correctness':correctness, 'final_completeness':completeness,
            'abstained':not emitted, 'abstention_appropriate':label['abstention_appropriate'],
            'review_note':label['note']})
    count = len(output)
    reviewed_final = [r['final_factual_correctness'] for r in output if type(r['final_factual_correctness']) is bool]
    return {'run_id':records[0]['run_id'], 'reviewer':review['reviewer'], 'review_basis':review['basis'],
        'cases':count, 'candidate_correct_count':sum(r['candidate_correct'] for r in output),
        'candidate_complete_count':sum(r['candidate_completeness']=='complete' for r in output),
        'final_correct_count':sum(reviewed_final), 'final_factual_correctness_denominator':len(reviewed_final),
        'final_factual_correctness':sum(reviewed_final)/len(reviewed_final) if reviewed_final else None,
        'final_complete_count':sum(r['final_completeness']=='complete' for r in output),
        'inappropriate_abstention_count':sum(r['abstained'] and not r['abstention_appropriate'] for r in output),
        'false_candidates_withheld':sum(not r['candidate_correct'] and r['abstained'] for r in output),
        'case_reviews':output,
        'note':'Assistant review against starter fixtures and deterministic checks, not independent human or source-backed ground truth. Final accuracy excludes abstentions and cannot be compared alone with candidate accuracy.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(latest_records(args.results),json.loads(args.review.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='case_reviews'},indent=2))


if __name__ == '__main__':
    main()
