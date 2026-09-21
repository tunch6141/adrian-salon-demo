from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import pytest
from analyst_engine import Database, QueryBlocked
from analytics.runtime import load_snapshot
from business_context import ContextStore
from commercial.models import Scope, Step, Diagnosis, Statement, Visual, Audit, ToolCall
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
    responses=[first,last,Audit(approved=True,problems=[])]
    try:
        with patch('commercial.runtime.model_call',side_effect=responses) as mock:
            result=investigate(None,'gpt-4.1-mini',db,'Show product revenue',[],ContextStore())
        assert result['status']=='answered' and result['display']['direct_answer']=='Revenue is 990.'
        assert result['analytical_state']['scope']['category']=='product'
        for c in mock.call_args_list:
            assert 'NEVER SEND THIS TO MODEL' not in str(c)
        assert len(result['execution_trace'])==1
    finally:db.close()


def test_no_current_citations_means_no_invented_answer():
    with pytest.raises(QueryBlocked):validate_answer(answer(),[],[],scope(),[],'lookup')
