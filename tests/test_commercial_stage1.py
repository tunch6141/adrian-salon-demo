from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import pytest
from analyst_engine import Database, QueryBlocked
from analytics.runtime import load_snapshot
from business_context import ContextStore
from commercial.models import Scope, Step, Diagnosis, Statement, Visual, Audit, ToolCall, Conclusion, EvidenceAssessment
from commercial.runtime import investigate, resolve_scope
from commercial.evidence import arithmetic, validate_answer


def scope(**kwargs):
    return Scope(**dict(objective='Understand revenue',subject='revenue',entities=['Sam'],start_date='2026-05-01',end_date='2026-08-31',measures=['net_revenue'],category='product',display='text')|kwargs)


def test_scope_inherits_fields_and_resets_on_new_topic():
    old=scope().model_dump()
    delta=Scope(**{k:None for k in old});delta.entities=['Sarah','Matthew']
    actual=resolve_scope(delta,old,'modify')
    assert actual.entities==['Sarah','Matthew'] and actual.category=='product' and actual.start_date=='2026-05-01'
    delta.objective='Assess inventory';delta.subject='inventory'
    fresh=resolve_scope(delta,old,'new')
    assert fresh.category=='' and fresh.start_date==''


def test_arithmetic_rejects_code_and_unknown_inputs():
    assert arithmetic('(v0-v1)/v1*100',{'v0':120,'v1':100})==20
    for expr in ['__import__("os")','v0**2','42','v0/0']:
        with pytest.raises(QueryBlocked):arithmetic(expr,{'v0':10})


def answer(**kwargs):
    base=dict(direct_answer=Statement(text='Revenue is [[0]].',evidence=[dict(result=0,row=0,column='revenue')],level='observed'),
        key_evidence=[],primary_driver=None,secondary_drivers=[],alternatives=[],confidence='insufficient evidence',
        next_step_kind='none',next_step=None,visual=Visual(),table_results=[],context_review=[],limitations='')
    return Diagnosis(**(base|kwargs))


def assessment():
    return EvidenceAssessment(outcome_status='factual_lookup',outcome_check='Requested value was retrieved.',supported_relationships=['Result 0 contains the requested amount.'],established_driver=None,unsupported_claims=[],next_evidence=[])


def test_action_and_composition_require_support():
    results=[dict(rows=[dict(revenue=990)])]
    with pytest.raises(QueryBlocked,match='supported primary'):
        validate_answer(answer(next_step_kind='action'),results,[],scope(),[],'lookup')
    result=answer(visual=Visual(kind='pie',result=1,x='item',y='revenue'))
    with pytest.raises(QueryBlocked,match='matching scoped total'):
        validate_answer(result,results+[dict(rows=[dict(item='a',revenue=7815)])],[],scope(),[],'lookup')


def test_active_path_does_not_import_legacy_prompts_or_recipes():
    folder=Path(__file__).resolve().parents[1]/'commercial'
    for f in folder.glob('*.py'):
        text=f.read_text(encoding='utf-8')
        assert 'from analyst_ai' not in text and 'analytics.reasoning' not in text and 'analytics.rules' not in text
        assert 'Sarah' not in text and 'Matthew' not in text
    ui=(folder.parent/'analyst_ui.py').read_text(encoding='utf-8')
    assert 'from commercial.runtime import investigate' in ui


def test_real_data_lookup_audited_and_state_saved_without_legacy_rules():
    db=Database.from_intake(load_snapshot(),rules_override='NEVER SEND THIS TO MODEL')
    call=ToolCall(kind='sql',purpose='Measure requested product revenue',sql="SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_name='Sam' AND item_type='product' AND posted_date BETWEEN '2026-05-01' AND '2026-08-31'")
    first=Step(intent='lookup',topic_relation='new',scope=scope(),hypotheses=[],calls=[call],final=None,draft=None,clarification='',unresolved=[])
    last=first.model_copy(deep=True);last.calls=[];last.final=answer();last.topic_relation='continue'
    responses=[first,last,assessment(),Conclusion(hypotheses=[],final=answer()),Audit(approved=True,problems=[])]
    try:
        with patch('commercial.runtime.model_call',side_effect=responses) as mock:
            result=investigate(None,'gpt-4.1-mini',db,'Show product revenue',[],ContextStore())
        assert result['status']=='answered' and result['display']['direct_answer']=='Revenue is 990.'
        assert result['analytical_state']['scope']['category']=='product'
        for c in mock.call_args_list:
            assert 'NEVER SEND THIS TO MODEL' not in str(c)
        assert len(result['execution_trace'])==1
        assessment_call=mock.call_args_list[2]
        assert 'answer' not in assessment_call.args[4] and 'hypotheses' not in assessment_call.args[4]
        assert result['evidence_assessment']['established_driver'] is None
    finally:db.close()


def test_no_current_citations_means_no_invented_answer():
    with pytest.raises(QueryBlocked):validate_answer(answer(),[],[],scope(),[],'lookup')


def test_numeric_prose_accepts_rounding_but_rejects_uncomputed_amounts():
    from commercial.evidence import render_statement
    statement=Statement(text='Revenue is AUD 123.46.',evidence=[dict(result=0,row=0,column='revenue')],level='observed')
    results=[dict(rows=[dict(revenue=123.456)])]
    assert render_statement(statement,results,scope())=='Revenue is AUD 123.46.'
    statement.text='The difference is AUD 100.00.'
    with pytest.raises(QueryBlocked):render_statement(statement,results,scope())
    statement.text='Revenue [[0,row:0,column:revenue]].'
    with pytest.raises(QueryBlocked,match='placeholder'):render_statement(statement,results,scope())


def test_reference_completion_only_links_existing_calculated_values():
    from commercial.evidence import complete_references,render_statement
    statement=Statement(text='The totals were 120 and 100, a difference of 20.',evidence=[dict(result=0,row=0,column='first'),dict(result=0,row=0,column='second')],level='observed')
    results=[dict(rows=[dict(first=120,second=100)]),dict(rows=[dict(difference=20)])]
    complete_references(statement,results)
    assert any(r.result==1 and r.column=='difference' for r in statement.evidence)
    assert render_statement(statement,results,scope())==statement.text
    statement.text='The totals differed by 30.'
    complete_references(statement,results)
    with pytest.raises(QueryBlocked):render_statement(statement,results,scope())


def test_result_citations_verify_numbers_without_model_cell_addresses():
    from commercial.evidence import render_statement
    statement=Statement(text='Revenue is 120; the difference is 20.',sources=[0],level='observed')
    results=[dict(rows=[dict(revenue=120,difference=20)])]
    assert render_statement(statement,results,scope())==statement.text
    statement.text='Revenue is 900.'
    with pytest.raises(QueryBlocked):render_statement(statement,results,scope())
    statement.text='Revenue was 2.6% lower.'
    assert render_statement(statement,[dict(rows=[dict(percentage_change=-2.62295)])],scope())==statement.text
    statement.text='The range is 6-18.'
    assert render_statement(statement,[dict(rows=[dict(low=6,high=18)])],scope())==statement.text
    statement.text='The amount is -18.'
    with pytest.raises(QueryBlocked):render_statement(statement,[dict(rows=[dict(amount=18)])],scope())


def test_unrelated_entity_note_is_reviewed_but_not_displayed():
    a=answer(context_review=[dict(context_id='note',relevance='relevant',interpretation='About pricing')])
    contexts=[dict(id='note',entity='Customer C90',customer_id='C90')]
    validate_answer(a,[dict(rows=[dict(revenue=90,staff_name='Sam')])],contexts,scope(),[],'lookup')
    assert a.context_review[0].relevance=='not_relevant'


def test_revenue_tools_resolve_the_same_staff_ids_as_performance():
    from commercial.evidence import execute
    db=Database.from_intake(load_snapshot(),rules_override='')
    try:
        person=db.intake.tables['staff'][0]
        for kind in ['revenue_total','revenue_trend']:
            result=execute(db,ToolCall(kind=kind,purpose='Read selected staff revenue',staff=[person['staff_id']],start_date='2026-08-01',end_date='2026-08-31'),[])
            assert result[0]['rows'][0]['staff_name']==person['staff_name']
    finally:db.close()


def test_reserved_conclusion_after_evidence_budget_and_case_insensitive_status():
    from commercial.models import Conclusion
    db=Database.from_intake(load_snapshot(),rules_override='')
    try:
        lower=db.query("SELECT COUNT(*) AS count FROM booking_records WHERE status='completed'")['rows'][0]['count']
        upper=db.query("SELECT COUNT(*) AS count FROM booking_records WHERE status='Completed'")['rows'][0]['count']
        assert lower==upper and lower>0
        steps=[]
        for month in ['05','06','08']:
            call=ToolCall(kind='sql',purpose='Investigate',sql=f"SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE posted_date LIKE '2026-{month}-%'")
            steps.append(Step(intent='lookup',topic_relation='new',scope=scope(),hypotheses=[],calls=[call],final=None,draft=None,clarification='',unresolved=[]))
        with patch('commercial.runtime.model_call',side_effect=steps+[assessment(),Conclusion(hypotheses=[],final=answer()),Audit(approved=True,problems=[])]) as mocked:
            result=investigate(None,'gpt-4.1-mini',db,'Read revenue',[],ContextStore())
        assert result['status']=='answered' and mocked.call_args_list[3].args[2] is EvidenceAssessment
        assert mocked.call_args_list[4].args[2] is Conclusion
        assert len(result['execution_trace'])==3
    finally:db.close()


def test_live_tool_protocol_and_grouped_cost_coverage():
    from commercial.evidence import execute
    db=Database.from_intake(load_snapshot(),rules_override='')
    try:
        people=db.intake.tables['staff']
        r=execute(db,ToolCall(kind='staff_performance',purpose='Compare staff',staff=[people[0]['staff_id']],start_date='2026-08-01',end_date='2026-08-31'),[])
        assert r[0]['rows'][0]['staff_name']==people[0]['staff_name']
        r=db.query("SELECT strftime('%Y-%m',posted_date) AS month, SUM(gross_profit) AS profit FROM financial_lines WHERE posted_date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY month")
        assert r['rows'][0]['profit']>0
        assert db.query("SELECT item_name FROM inventory_coverage WHERE item_name LIKE '%shampoo%'")['rows']
        with pytest.raises(QueryBlocked,match='one period'):
            execute(db,ToolCall(kind='revenue_total',purpose='Compare',comparison_start='2026-07-01'),[])
        with pytest.raises(QueryBlocked,match='kind=sql'):
            execute(db,ToolCall(kind='booking',purpose='Count',sql='SELECT COUNT(*) FROM booking_records'),[])
        # A null-cost line must still prevent a complete margin being reported.
        from types import SimpleNamespace
        import pandas as pd
        small=Database.__new__(Database);small.intake=SimpleNamespace(revision='cost-test')
        small._open_frames({'financial_lines':pd.DataFrame([{'posted_date':'2026-08-01','gross_profit':5},{'posted_date':'2026-08-02','gross_profit':None}])})
        try:
            with pytest.raises(QueryBlocked,match='incomplete'):
                small.query("SELECT strftime('%Y-%m',posted_date) AS month, SUM(gross_profit) AS profit FROM financial_lines GROUP BY month")
        finally:small.close()
    finally:db.close()
