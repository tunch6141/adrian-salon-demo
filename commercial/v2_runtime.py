"""Native tool investigation with scope enforcement and review inside the loop."""
import json
import math
import time
from datetime import date,timedelta
from pydantic import ValidationError
from openai import pydantic_function_tool
from analyst_engine import QueryBlocked, validate_claim_numbers, validate_chart
from analytics.diagnostics import calendar_periods, booking_lookup, comparable_periods
from .v2_models import (AnalysisScope, FrameQuestion, QueryData, ReadRecords,
                        StaffPerformance, ReadSQL, FinishAnswer, Review, BookingRecord, QueryCurrentData, ComparePeriods)
from .v2_data import catalog, resolve_entities, query_data, read_records, staff_performance, read_sql
from .v2_prompts import SYSTEM, REVIEW

ANSWER_RELEASE='21 Sep 2026 · commercial tools 2'
MAX_ROUNDS=8
MAX_DATA_CALLS=10
TOOLS={
 'frame_question':(FrameQuestion,'Establish or correct the commercial objective, scope, hypotheses or essential clarification before retrieving data.'),
 'query_data':(QueryCurrentData,'Retrieve totals or a time trend within ONE current/baseline period. Active scope is applied automatically. Ratios use the same source rows. For current-versus-baseline changes use compare_periods.'),
 'compare_periods':(ComparePeriods,'Calculate current versus baseline totals, differences and percentage changes for the matched periods declared in frame_question. Optional dimensions compare each group. No time buckets.'),
 'read_records':(ReadRecords,'Read selected individual cleaned records with active scope. Use exact filters for bookings, customers or other record IDs.'),
 'booking_record':(BookingRecord,'Retrieve an individual cleaned booking by its identifier, including a uniquely resolvable zero-padding variant. An exact record request is independent of the current reporting period.'),
 'staff_performance':(StaffPerformance,'Retrieve trusted staff revenue, completed service hours, capacity, utilisation and service mix for the active people and dates, with optional matched-period comparison.'),
 'read_sql':(ReadSQL,'Fallback for calculations not expressible by query_data. Read-only SQLite on one catalogue view. Active dates, people and category are added automatically.'),
 'finish_answer':(FinishAnswer,'Submit a concise evidence-grounded commercial answer. Checks can return feedback; correct or investigate further while budget remains. Charts are optional and cannot block a supported answer.')}


def tool_schema(name):
    model,description=TOOLS[name]
    function=pydantic_function_tool(model,name=name,description=description)['function']
    return {'type':'function',**function}


def resolve_scope(patch,previous,relation,calendar):
    old=previous or {} if relation!='new' else {}
    defaults=dict(objective='',subject='',entities=[],start_date='',end_date='',comparison_start='',comparison_end='',category='all',measures=[],display='text')
    data={k:(v if v is not None else old.get(k,defaults[k])) for k,v in patch.model_dump().items()}
    if not data['objective']:raise QueryBlocked('State the commercial objective.')
    for key in ['start_date','end_date','comparison_start','comparison_end']:
        if data[key]:date.fromisoformat(data[key])
    if bool(data['start_date'])!=bool(data['end_date']):raise QueryBlocked('Provide both start and end dates, or neither for a snapshot.')
    if data['start_date']>data['end_date']:raise QueryBlocked('The period is reversed.')
    if bool(data['comparison_start'])!=bool(data['comparison_end']) or data['comparison_start']>data['comparison_end']:
        raise QueryBlocked('Provide a complete, ordered comparison period.')
    if data['comparison_start'] and not comparable_periods(data['start_date'],data['end_date'],data['comparison_start'],data['comparison_end'],1):
        raise QueryBlocked('Declare matched current and baseline periods separately. Calendar options: '+json.dumps(calendar))
    return AnalysisScope(**data)


def report_calendar(intake):
    result=calendar_periods(intake);today=intake.asof.date();last=today.replace(day=1)-timedelta(days=1)
    monday=today-timedelta(days=today.weekday())
    result.update(current_month_elapsed=[str(today.replace(day=1)),str(today)],
                  previous_month_matched_elapsed=[str(last.replace(day=1)),str(last.replace(day=min(today.day,last.day)))],
                  next_week=[str(monday+timedelta(days=7)),str(monday+timedelta(days=13))])
    return result


def context_candidates(store,db,scope):
    identities=resolve_entities(db,scope.entities)
    names=[p['name'] for p in identities] or ['Salon']
    names.extend('Customer '+p['value'] for p in identities if p['key']=='customer_id')
    notes=[]
    for name in names:notes.extend(store.search(name,scope.start_date,scope.end_date))
    # A broad store search may include every entity. Only matching identities and
    # business-wide notes are evidence for this scope.
    return list({r['id']:r for r in notes if r['entity'] in [*names,'Salon']}.values())[:12]


def _timing(stats,name,response,started):
    usage=getattr(response,'usage',None)
    stats.append(dict(stage=name,seconds=round(time.monotonic()-started,2),
        input_tokens=getattr(usage,'input_tokens',0),output_tokens=getattr(usage,'output_tokens',0)))


def validate_report(report,results,scope,contexts):
    byid={p['evidence_id']:i for i,p in enumerate(results)}
    if not report.sources and results:raise QueryBlocked('Cite the Evidence IDs supporting the answer.')
    if not set(report.sources)<=set(byid):raise QueryBlocked('Unknown Evidence ID. Use only '+', '.join(byid))
    refs=[];check_results=[]
    for p in results:
        meta=p.get('metadata',{});rows=list(p['rows'])
        if meta.get('scoped_totals'):rows.append(meta['scoped_totals'])
        check_results.append(dict(p,rows=rows))
    for evidence_id in report.sources:
        i=byid[evidence_id]
        refs.extend(dict(result=i,row=j,column=k) for j,row in enumerate(check_results[i]['rows']) for k in row)
    text='\n'.join([report.answer,*report.evidence,report.explanation,report.next_step,report.limitations])
    validate_claim_numbers(check_results,dict(text=text,evidence=refs),report.context_used,
        [scope.start_date,scope.end_date,scope.comparison_start,scope.comparison_end],allow_magnitude=True)
    if not set(report.context_used)<={r['id'] for r in contexts}:raise QueryBlocked('Only supplied context note IDs may be cited.')
    return [byid[key] for key in report.sources]


def optional_chart(report,results):
    chart=report.chart;byid={p['evidence_id']:i for i,p in enumerate(results)}
    none=dict(kind='none',result=0,x='',y='',series='')
    if chart.kind=='none':return none,''
    try:
        if chart.source not in byid:raise QueryBlocked('The chart source was not retrieved.')
        i=byid[chart.source];spec=dict(kind=chart.kind,result=i,x=chart.x,y=chart.y,series=chart.series)
        validate_chart(results,spec)
        if chart.kind=='pie':
            p=results[i];rows=p['rows'];meta=p.get('metadata',{})
            total=meta.get('scoped_totals',{}).get(chart.y)
            if chart.series or len(rows)>6 or not meta.get('complete_result') or total is None or not math.isclose(sum(r[chart.y] for r in rows),total,abs_tol=.005):
                raise QueryBlocked('A pie needs a complete, small composition matching the same scoped total.')
        return spec,''
    except (QueryBlocked,KeyError,TypeError):
        return none,'The requested visual could not be validated; the verified answer is shown without it.'


def adapt_report(report,results,scope,contexts,indices):
    visual,notice=optional_chart(report,results)
    statement=lambda text:dict(text=text,sources=indices,evidence=[],context_ids=[],level='supported_interpretation')
    byid={p['evidence_id']:i for i,p in enumerate(results)}
    selected=[byid[report.table_source]] if report.table_source in byid else []
    notes=[dict(context_id=n['id'],relevance='relevant' if n['id'] in report.context_used else 'not_relevant',interpretation='Owner-reported context considered; not independently established cause.') for n in contexts]
    answer=dict(direct_answer=statement(report.answer),key_evidence=[statement(x) for x in report.evidence],primary_driver=None,
                secondary_drivers=[statement(report.explanation)] if report.explanation else [],alternatives=[],confidence=report.confidence,
                next_step_kind='investigation' if report.confidence in ['insufficient evidence','possible explanation'] else 'action',
                next_step=statement(report.next_step) if report.next_step else None,visual=visual,table_results=selected,context_review=notes,
                limitations=' '.join(x for x in [report.limitations,notice] if x))
    display=dict(direct_answer=report.answer,key_evidence=report.evidence,primary_driver='',secondary_drivers=[report.explanation] if report.explanation else [],alternatives=[],next_step=report.next_step)
    return answer,display


def investigate(client,model,db,question,history,context_store,on_stage=None,active_state=None):
    started=time.monotonic();stage=on_stage or (lambda _:None);stats=[];trace=[];results=[];contexts=[];reviews=[];errors=[]
    state=active_state or next((h.get('analytical_state') for h in reversed(history) if h.get('analytical_state')),None)
    if state and state.get('snapshot_id')!=db.intake.revision:state={**state,'findings':[],'hypotheses':[]}
    calendar=report_calendar(db.intake)
    initial=dict(question=question,active_state=state,reporting_calendar=calendar,
                 available_staff=db.intake.tables.get('staff',[]),catalog=catalog(db),
                 snapshot_id=db.intake.revision,unresolved_data_issues=len(db.intake.issues))
    messages=[dict(role='user',content=json.dumps(initial,default=str))]
    frame=None;scope=AnalysisScope();answer=None;display=None;candidate=None;count=0;seen=set();status='facts_only'
    for round_index in range(MAX_ROUNDS):
        stage('Understanding your business question' if frame is None else 'Investigating the evidence')
        names=['frame_question'] if frame is None else list(TOOLS)
        if round_index==MAX_ROUNDS-1:names=['finish_answer']
        request_started=time.monotonic()
        response=client.responses.create(model=model,instructions=SYSTEM,input=messages,tools=[tool_schema(n) for n in names],
            tool_choice='required',parallel_tool_calls=len(names)>1,max_output_tokens=2400,temperature=0.1,store=False)
        _timing(stats,'investigation',response,request_started)
        messages.extend([item.model_dump(exclude_none=True) for item in response.output])
        calls=[item for item in response.output if item.type=='function_call']
        if not calls:
            messages.append(dict(role='user',content='Use an available tool; finish_answer submits the final answer.'));continue
        for call in calls:
            output={};call_started=time.monotonic()
            try:
                if call.name not in names:raise QueryBlocked('This tool is not currently available.')
                request=TOOLS[call.name][0].model_validate_json(call.arguments)
                if call.name=='frame_question':
                    prior=scope.model_dump() if frame else (state or {}).get('scope')
                    scope=resolve_scope(request.scope,prior,request.relation if not frame else 'continue',calendar)
                    if request.intent not in ['context','clarify']:resolve_entities(db,scope.entities)
                    frame=request
                    if frame.intent in ['context','clarify']:
                        status=frame.intent;break
                    contexts=context_candidates(context_store,db,scope)
                    output=dict(scope=scope.model_dump(),owner_context=contexts,remaining_data_calls=MAX_DATA_CALLS-count)
                elif call.name=='finish_answer':
                    candidate=request
                    if frame is None:raise QueryBlocked('Frame the question before answering.')
                    if any(c.name not in ['frame_question','finish_answer'] for c in calls):raise QueryBlocked('Read the data-tool results before submitting the answer.')
                    indices=validate_report(request,results,scope,contexts)
                    stage('Checking the commercial explanation')
                    review_started=time.monotonic()
                    review_response=client.responses.parse(model=model,instructions=REVIEW,text_format=Review,
                        input=json.dumps(dict(question=question,scope=scope.model_dump(),answer=request.model_dump(),results=results,contexts=contexts),default=str),
                        max_output_tokens=1000,temperature=0,store=False)
                    _timing(stats,'review',review_response,review_started)
                    review=review_response.output_parsed
                    if review is None:raise QueryBlocked('The evidence review did not complete.')
                    reviews.append(review.model_dump())
                    if review.blocking_errors or review.unsupported_statements:
                        errors=review.blocking_errors+review.unsupported_statements
                        output=dict(accepted=False,blocking_errors=errors,evidence_needed=review.evidence_needed,
                                    remaining_data_calls=MAX_DATA_CALLS-count,remaining_rounds=MAX_ROUNDS-round_index-1)
                    else:
                        answer,display=adapt_report(request,results,scope,contexts,indices)
                        status='answered';errors=[];break
                else:
                    if frame is None:raise QueryBlocked('Frame the question before retrieving data.')
                    if count>=MAX_DATA_CALLS:raise QueryBlocked('Data-call budget reached. Give the supported answer with remaining uncertainty.')
                    signature=call.name+scope.model_dump_json()+request.model_dump_json(exclude={'purpose'})
                    if signature in seen:raise QueryBlocked('This exact request was already made; use its results or change the investigation.')
                    if call.name=='compare_periods':new=query_data(db,QueryData(**request.model_dump(),period='compare'),scope)
                    elif call.name=='booking_record':new=booking_lookup(db,request.identifier)
                    else:new={'query_data':query_data,'read_records':read_records,'staff_performance':staff_performance,'read_sql':read_sql}[call.name](db,request,scope)
                    seen.add(signature)
                    count+=1
                    for p in new:p['evidence_id']='E'+str(len(results)+1);results.append(p)
                    # Only one citation identifier reaches the model. Internal packet
                    # hashes and table names are not competing citation conventions.
                    output=dict(evidence=[{k:p[k] for k in ['evidence_id','rows','metadata'] if k in p} for p in new],remaining_data_calls=MAX_DATA_CALLS-count,remaining_rounds=MAX_ROUNDS-round_index-1)
                    trace.append(dict(tool=call.name,request=request.model_dump(),sources=[p['evidence_id'] for p in new],status='ok'))
            except (QueryBlocked,ValidationError,ValueError,KeyError,TypeError) as exc:
                errors=[str(exc)];output=dict(error=str(exc),remaining_data_calls=MAX_DATA_CALLS-count)
                trace.append(dict(tool=call.name,status='rejected',error=str(exc)))
            except Exception as exc:
                import sqlite3
                from sqlglot.errors import SqlglotError
                if not isinstance(exc,(sqlite3.Error,SqlglotError)):raise
                errors=[str(exc)];output=dict(error=str(exc))
                trace.append(dict(tool=call.name,status='rejected',error=str(exc)))
            messages.append(dict(type='function_call_output',call_id=call.call_id,output=json.dumps(output,default=str)))
        if status in ['answered','context','clarify']:break
    saved=dict(scope=scope.model_dump(),last_question=question,snapshot_id=db.intake.revision,
               hypotheses=frame.hypotheses if frame else [],findings=[display['direct_answer'],*display['key_evidence']] if display else [],unresolved=errors)
    result=dict(engine='commercial_native_tools',answer_release=ANSWER_RELEASE,status=status,
                plan=dict(scope=scope.model_dump(),draft=frame.context_draft.model_dump() if frame and frame.context_draft else None,
                          missing_information=frame.clarification if frame else ''),answer=answer,results=results,contexts=contexts,
                issues=errors,execution_trace=trace,analytical_state=saved,
                hypothesis_tests=candidate.tested_explanations if candidate else (frame.hypotheses if frame else []),
                candidate_answer=candidate.model_dump() if candidate else None,audit_reviews=reviews,
                reporting_date=str(db.intake.asof.date()),timing=dict(total_seconds=round(time.monotonic()-started,2),calls=stats))
    if display:result['display']=display
    return result
