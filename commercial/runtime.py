"""Bounded problem/hypothesis/evidence loop for the active Stage 1 runtime."""
import json
import time
from datetime import date
from datetime import timedelta
from analyst_engine import QueryBlocked
from analytics.diagnostics import calendar_periods
from .models import Step, Audit, Scope
from .contract import CONTRACT, DATA_DEFINITIONS, AUDIT
from .evidence import TOOLS, execute, validate_answer, statements

ANSWER_RELEASE='21 Sep 2026 · Stage 1 commercial reasoning'
MAX_STEPS=4
MAX_TOOLS=9


def resolve_scope(patch,previous,relation):
    base=(previous or {}) if relation!='new' else {}
    values={k:(v if v is not None else base.get(k)) for k,v in patch.model_dump().items()}
    if not values['objective']:raise QueryBlocked('State the business objective before investigating.')
    defaults={'subject':'','entities':[],'start_date':'','end_date':'','measures':[],'category':'','display':'text'}
    return Scope(**{k:(v if v is not None else defaults.get(k)) for k,v in values.items()})


def model_call(client,model,schema,instructions,payload,stats):
    started=time.monotonic()
    result=client.responses.parse(model=model,instructions=instructions,input=json.dumps(payload,default=str),
        text_format=schema,max_output_tokens=4500,temperature=0.2,store=False)
    stats.append(dict(stage=schema.__name__,seconds=round(time.monotonic()-started,2),
        input_tokens=getattr(result.usage,'input_tokens',0),output_tokens=getattr(result.usage,'output_tokens',0)))
    if result.output_parsed is None:raise QueryBlocked('The model did not return a complete structured response.')
    return result.output_parsed


def context_for(store,scope):
    rows=[]
    for entity in scope.entities or ['Salon']:
        rows+=store.search(entity,scope.start_date,scope.end_date)
    return list({r['id']:r for r in rows}.values())[:12]


def investigate(client,model,db,question,history,context_store,on_stage=None,active_state=None):
    stage=on_stage or (lambda _:None)
    started=time.monotonic();stats=[];results=[];trace=[];errors=[];seen=set();contexts=[]
    # New runtime never reads legacy history plans, rules, or reasoning graph.
    state=active_state or next((h['analytical_state'] for h in reversed(history) if h.get('analytical_state')),None)
    if state and state.get('snapshot_id')!=db.intake.revision:
        state={**state,'findings':[],'hypotheses':[],'unresolved':['Data changed; recheck previous findings.']}
    calendar=calendar_periods(db.intake)
    today=db.intake.asof.date();monday=today-timedelta(days=today.weekday())
    calendar.update(current_month_elapsed=[str(today.replace(day=1)),str(today)],
                    next_week=[str(monday+timedelta(days=7)),str(monday+timedelta(days=13))])
    payload=dict(question=question,active_state=state,schema=db.schema,tools=TOOLS,
        reporting_calendar=calendar,
        available_staff=[dict(staff_id=r['staff_id'],staff_name=r['staff_name']) for r in db.intake.tables.get('staff',[])],
        data_quality={'unresolved_issues':len(db.intake.issues),'snapshot_id':db.intake.revision})
    step=None;answer=None;rendered={};status='facts_only';tool_count=0
    for round_index in range(MAX_STEPS):
        stage('Understanding the business question' if round_index==0 else 'Testing the commercial explanation')
        payload.update(results=[dict(r,result_index=i) for i,r in enumerate(results)],contexts=contexts,execution_trace=trace,validation_feedback=errors,
                       remaining_steps=MAX_STEPS-round_index-1,remaining_tools=MAX_TOOLS-tool_count)
        if step:payload['current_investigation']=step.model_dump(exclude={'final'})
        previous_scope=step.scope.model_dump() if step else (state or {}).get('scope')
        try:step=model_call(client,model,Step,CONTRACT+'\n'+DATA_DEFINITIONS,payload,stats)
        except Exception as exc:
            from pydantic import ValidationError
            if not isinstance(exc,ValidationError):raise
            errors=['The response was incomplete. Return a compact valid Step with short statements and no repeated whitespace.']
            continue
        try:step.scope=resolve_scope(step.scope,previous_scope,step.topic_relation if round_index==0 else 'continue')
        except QueryBlocked as exc:
            errors=[str(exc)];continue
        if step.intent=='context':status='context';break
        if step.intent=='clarify':status='clarify';break
        scope=step.scope
        try:
            if scope.start_date:date.fromisoformat(scope.start_date)
            if scope.end_date:date.fromisoformat(scope.end_date)
            if scope.start_date and scope.end_date and scope.start_date>scope.end_date:raise ValueError('Reversed period')
        except ValueError:
            errors=['Use a valid inclusive ISO date range.'];continue
        new_context=context_for(context_store,scope)
        changed_context={c['id'] for c in new_context}!={c['id'] for c in contexts}
        contexts=new_context
        if step.calls:
            if round_index==MAX_STEPS-1:
                errors=['Investigation limit reached; additional requested calculations were not run.'];break
            errors=[]
            for call in step.calls:
                signature=json.dumps(call.model_dump(exclude={'purpose','label'}),sort_keys=True)
                if signature in seen:
                    errors.append('This tool call was already executed. Reuse its evidence.');continue
                if tool_count>=MAX_TOOLS:
                    errors.append('Tool budget reached; report the remaining uncertainty.');break
                seen.add(signature);tool_count+=1
                try:
                    new=execute(db,call,results)
                    indices=list(range(len(results),len(results)+len(new)))
                    results.extend(new)
                    trace.append(dict(call=call.model_dump(),results=indices,status='ok'))
                except (ValueError,KeyError,TypeError) as exc:
                    errors.append(str(exc));trace.append(dict(call=call.model_dump(),status='rejected',error=str(exc)))
                except Exception as exc:
                    # SQLite/parser failures are tool feedback; never expose credentials.
                    import sqlite3
                    from sqlglot.errors import SqlglotError
                    if not isinstance(exc,(sqlite3.Error,SqlglotError)):raise
                    errors.append(str(exc));trace.append(dict(call=call.model_dump(),status='rejected',error=str(exc)))
            continue
        if step.final is None:
            errors=['Provide a supported answer or request necessary evidence.'];continue
        if changed_context:
            errors=['New matching owner context was retrieved. Review it before finalising.'];continue
        try:
            rendered=validate_answer(step.final,results,contexts,scope,step.hypotheses,step.intent)
        except QueryBlocked as exc:
            errors=[str(exc)]
            payload['rejected_answer']=step.final.model_dump()
            continue
        stage('Checking the diagnosis against the evidence')
        audit=model_call(client,model,Audit,AUDIT+'\n'+DATA_DEFINITIONS,
            dict(question=question,active_state=state,scope=scope.model_dump(),hypotheses=[h.model_dump() for h in step.hypotheses],
                 answer=step.final.model_dump(),rendered_statements=list(rendered.values()),results=results,contexts=contexts,trace=trace),stats)
        if not audit.approved:
            errors=audit.problems;continue
        answer=step.final;status='answered';errors=[];break
    scope=step.scope.model_dump() if step else {}
    saved_state=dict(scope=scope,last_question=question,snapshot_id=db.intake.revision,
        hypotheses=[dict(explanation=h.explanation,status=h.status,test=h.test) for h in step.hypotheses] if step else [],
        findings=list(rendered.values())[:6] if answer else [],unresolved=step.unresolved if step else errors)
    result=dict(engine='commercial_stage1',answer_release=ANSWER_RELEASE,status=status,
        plan=dict(scope=scope,draft=step.draft.model_dump() if step and step.draft else None,
                  missing_information=step.clarification if step else ''),
        answer=answer.model_dump() if answer else None,results=results,contexts=contexts,issues=errors,
        execution_trace=trace,analytical_state=saved_state,
        hypothesis_tests=[h.model_dump() for h in step.hypotheses] if step else [],
        reporting_date=db.intake.asof.date().isoformat(),
        timing=dict(total_seconds=round(time.monotonic()-started,2),calls=stats))
    if answer:
        result['display']=dict(direct_answer=rendered[id(answer.direct_answer)],
            key_evidence=[rendered[id(s)] for s in answer.key_evidence],
            primary_driver=rendered[id(answer.primary_driver)] if answer.primary_driver else '',
            secondary_drivers=[rendered[id(s)] for s in answer.secondary_drivers],
            alternatives=[rendered[id(s)] for s in answer.alternatives],
            next_step=rendered[id(answer.next_step)] if answer.next_step else '')
    return result
