"""Repeatable behavioural evaluation. No benchmark content enters runtime prompts."""
from copy import deepcopy
import json
from pydantic import BaseModel, Field
from analyst_engine import Database
from analytics.runtime import CombinedContextStore
from business_context import ContextStore
from commercial.v2_runtime import investigate
from commercial.runtime import model_call

CORE=[
 ('revenue','Why was my revenue lower this month compared with last month?'),
 ('capacity','Why is next week looking quiet?'),
 ('staff','How is Sarah performing compared with Matthew?'),
 ('customers','Why are fewer customers coming back?'),
 ('services','Which services are actually making me the most money?'),
 ('inventory','Which products am I holding too much stock of?'),
 ('busy_profit','Why do we feel really busy but we are not making enough profit?'),
 ('sales_profit','Sales are increasing, so why is my profit getting worse?'),
 ('followup','Okay, what is actually going wrong with Sarah?')]
PARAPHRASES=[
 ('revenue','Has turnover really deteriorated, and what explains it?'),
 ('capacity','Do we have a demand problem in the coming week or just space in the diary?'),
 ('staff','Compare the commercial contribution of Matthew and Sarah.'),
 ('customers','Are our regulars visiting less often, or am I imagining it?'),
 ('services','Where are our services contributing value after their recorded costs?'),
 ('inventory','What stock is tying up money unnecessarily?'),
 ('busy_profit','The team seems flat out. Why might that not translate into worthwhile earnings?'),
 ('sales_profit','Turnover looks healthy but earnings do not. Can the records explain that?')]

JUDGE='''Evaluate commercial behaviour, not exact wording. Assess whether the answer
addresses the question, selects useful evidence dynamically, tests competing
explanations, reasons across domains when needed, quantifies material drivers,
respects incomplete costs/periods/uncertainty, avoids metric dumping, preserves
follow-up scope, and recommends a supported action or a next investigation.
Check the actual retrieved data and tool calls; do not reward plausible prose
alone. A corrected false premise or qualified insufficient-evidence answer can
pass. For analytical answers, a bare metric report is a failure. Return each
criterion as a boolean and concrete issues. Do not assign fake confidence scores.
For a factual lookup or ranking, relevant supported facts can fully answer the
request; do not demand causal hypotheses, a trend investigation or an action
that the question does not call for. Mark those criteria satisfied when not needed.
This judge is an automated assessment requiring owner review, not certification.'''


class Grade(BaseModel):
    objective_understood: bool
    evidence_relevant: bool
    conclusion_supported: bool
    competing_explanations_checked: bool
    uncertainty_respected: bool
    concise_and_useful: bool
    next_step_appropriate: bool
    issues: list[str] = Field(max_length=8)


def cases():
    return [dict(id=k,question=q,variant='base',group='core') for k,q in CORE]+[
        dict(id=k+'_paraphrase',question=q,variant='base',group='paraphrase') for k,q in PARAPHRASES]+[
        dict(id='renamed_staff',question='How does Priya compare with Jordan commercially?',variant='renamed',group='renamed'),
        dict(id='renamed_product',question='Is Ocean Wash creating an inventory problem?',variant='renamed',group='renamed'),
        dict(id='changed_staff',question='Compare Sarah and Matthew in August. What explains the revenue gap?',variant='changed',group='changed_data'),
        dict(id='base_staff_august',question='Compare Sarah and Matthew in August. What explains the revenue gap?',variant='base',group='changed_data_control'),
        dict(id='unseen_refunds',question='Are refunds concentrated in any service or member of staff?',variant='base',group='unseen'),
        dict(id='unseen_supplier',question='Do the records establish which supplier is costing us more for comparable stock?',variant='base',group='unseen')]


def fixture(intake,variant):
    t=deepcopy(intake)
    if variant=='renamed':
        mapping={'Sarah':'Priya','Matthew':'Jordan','Sam':'Alex'}
        for row in t.tables.get('staff',[]):row['staff_name']=mapping.get(row['staff_name'],row['staff_name'])
        for row in t.tables.get('items',[]):
            if row['item_name']=='Colour care shampoo':row['item_name']='Ocean Wash'
        for row in t.contexts:
            for old,new in mapping.items():
                row['entity']=row['entity'].replace(old,new);row['explanation']=row['explanation'].replace(old,new)
    if variant=='changed':
        from decimal import Decimal
        sid=next(r['staff_id'] for r in t.tables['staff'] if r['staff_name']=='Sarah')
        for row in t.tables['transaction_items']:
            if row['staff_id']==sid:row['net_amount_ex_gst']=str(Decimal(str(row['net_amount_ex_gst']))*2)
    t.revision=intake.revision+':evaluation:'+variant
    return t


def run(client,model,intake,selected=None,on_case=None,on_result=None,initial_staff_state=None):
    reports=[];staff_state=initial_staff_state
    for case in cases():
        if selected and case['id'] not in selected:continue
        if on_case:on_case(case['id'],len(reports))
        t=fixture(intake,case['variant']);db=Database.from_intake(t,rules_override='Evaluation uses commercial contract only.')
        try:
            result=investigate(client,model,db,case['question'],[],CombinedContextStore(t,ContextStore()),active_state=staff_state if case['id']=='followup' else None)
            if case['id']=='staff':staff_state=result['analytical_state']
            grade=None
            if result['status']=='answered':
                grade=model_call(client,'gpt-4.1-mini',Grade,JUDGE,dict(question=case['question'],previous_state=staff_state if case['id']=='followup' else None,
                    answer=result['display'],diagnosis=result['answer'],hypotheses=result['hypothesis_tests'],scope=result['analytical_state']['scope'],
                    evidence=result['results'],trace=result['execution_trace']),[]).model_dump()
            reports.append(dict(**case,model=model,judge_model='gpt-4.1-mini',status=result['status'],grade=grade,
                passed=bool(grade and all(v for k,v in grade.items() if k!='issues')),result=result))
        except Exception as exc:
            reports.append(dict(**case,status='error',passed=False,error=type(exc).__name__+': '+str(exc)))
        finally:db.close()
        if on_result:on_result(reports)
    return reports


if __name__=='__main__':
    import argparse,os
    from pathlib import Path
    from openai import OpenAI
    from analytics.runtime import load_snapshot
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--cases',nargs='*');args=p.parse_args()
    results=run(OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=60,max_retries=0),'gpt-4.1-mini',load_snapshot(),args.cases,lambda name,n:print(name,flush=True))
    Path(args.output).write_text(json.dumps(results,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'passed':sum(r['passed'] for r in results),'total':len(results)}))
