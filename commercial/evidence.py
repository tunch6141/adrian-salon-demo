"""Trusted tool execution and arithmetic. No question routing or model prompts."""
import ast
import math
import operator
import re
from analyst_engine import QueryBlocked, reference_value, validate_claim_numbers, validate_chart
from analytics.diagnostics import packet, staff_diagnostic, period_diagnostic, revenue_diagnostic, revenue_trend, booking_lookup


TOOLS = {
    'sql':'One SQLite SELECT from a view listed in schema, using its exact columns. No joins/subqueries/UNION/windows. Separate calls for separate queries. strftime for month/year, never DATE_TRUNC or EXTRACT. Returned result packets are not SQL views.',
    'staff_performance':'Matched staff revenue, completed service hours, available capacity, utilisation, service mix and optional comparable-period changes. Explicit staff and dates required.',
    'revenue_total':'Inclusive-period posted net service, product, part and total revenue by requested staff or whole business.',
    'revenue_trend':'Calendar day/week/month revenue by category and staff, with exact totals, changes and partial-period coverage.',
    'booking':'One cleaned booking by exact ID or unique zero-padding variant.',
    'calculate':'Exact arithmetic across returned numeric cells; expression v0,v1... references inputs. Use to quantify differences, ratios or contributions, never invent a business input.'
}


def arithmetic(expression, values):
    if len(expression)>300:raise QueryBlocked('Calculation expression is too long.')
    ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
    def walk(node):
        if isinstance(node,ast.Expression):return walk(node.body)
        if isinstance(node,ast.Name) and node.id in values:return values[node.id]
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):return node.value
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return walk(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
        if isinstance(node,ast.BinOp) and type(node.op) in ops:return ops[type(node.op)](walk(node.left),walk(node.right))
        raise QueryBlocked('Only arithmetic over referenced values is permitted.')
    try:
        tree=ast.parse(expression,mode='eval')
        if not any(isinstance(n,ast.Name) for n in ast.walk(tree)):raise QueryBlocked('Calculation must use returned evidence.')
        result=walk(tree)
        if not math.isfinite(result):raise QueryBlocked('Calculation is not finite.')
        return result
    except (SyntaxError,ZeroDivisionError,TypeError,OverflowError) as exc:
        raise QueryBlocked('Calculation unavailable: invalid expression or missing/zero denominator.') from exc


def execute(db,call,results):
    if call.kind=='sql':return [db.query(call.sql)]
    if call.kind=='booking':
        if call.sql:raise QueryBlocked('Use kind=sql to run SQL. booking only retrieves an actual booking ID.')
        return booking_lookup(db,call.identifier)
    if call.kind=='calculate':
        values={f'v{i}':reference_value(results,r.model_dump()) for i,r in enumerate(call.inputs)}
        if any(type(v) not in (int,float) for v in values.values()):raise QueryBlocked('Arithmetic inputs must be known numeric evidence.')
        value=arithmetic(call.expression,values)
        return [packet(db.intake,'calculated_relationship',[{'label':call.label,'value':value}],call.expression+'; '+str([r.model_dump() for r in call.inputs]))]
    names={str(r['staff_id']):r['staff_name'] for r in db.intake.tables.get('staff',[])}
    staff=[names.get(s,s) for s in call.staff]
    if call.kind=='staff_performance':
        staff=staff or list(names.values())
        if call.comparison_start or call.comparison_end:
            return period_diagnostic(db,staff,call.start_date,call.end_date,call.comparison_start,call.comparison_end,call.comparison_divisor)
        return staff_diagnostic(db,staff,call.start_date,call.end_date)
    if call.kind=='revenue_total':
        if call.comparison_start or call.comparison_end:raise QueryBlocked('revenue_total returns one period only. Use separate calls for each period, or revenue_trend for several periods.')
        return revenue_diagnostic(db,staff,call.start_date,call.end_date)
    if call.kind=='revenue_trend':return revenue_trend(db,staff,call.start_date,call.end_date,call.grain,call.category)
    raise QueryBlocked('Unknown evidence tool.')


def statements(answer):
    return [s for s in [answer.direct_answer,*answer.key_evidence,answer.primary_driver,*answer.secondary_drivers,*answer.alternatives,answer.next_step] if s]


def render_statement(statement,results,scope):
    refs=[r.model_dump() for r in statement.evidence]
    values=[reference_value(results,r) for r in refs]
    text=statement.text
    slots={'start':scope.start_date or '', 'end':scope.end_date or ''}
    for i,(ref,value) in enumerate(zip(refs,values)):
        if type(value) in (int,float):
            value=(f'AUD {value:,.2f}' if ref['format']=='money' else
                   f'{value:,.2f}%' if ref['format']=='percent' else f'{value:,.2f}'.rstrip('0').rstrip('.'))
        slots[str(i)]=str(value) if value is not None else 'unknown'
    for slot in re.findall(r'\[\[(.*?)\]\]',text):
        if slot not in slots:raise QueryBlocked('Invalid value placeholder. Use plain numeric prose with evidence references, or only [[0]], [[1]], [[start]], [[end]]. Never embed reference objects in the sentence.')
    # Plain numeric prose is accepted only if each value faithfully rounds a cited
    # cell. Derived amounts must first be calculated. The independent audit checks
    # that citations support the entire meaning, units, scope and comparison.
    literal=re.sub(r'\[\[.*?\]\]','',text)
    try:validate_claim_numbers(results,dict(text=literal,evidence=refs),statement.context_ids,[scope.start_date,scope.end_date])
    except QueryBlocked as exc:
        raise QueryBlocked(f'{exc} Sentence: {text!r}; cited values: {values!r}. Cite each displayed value, or omit an uncomputed number.') from exc
    return re.sub(r'\[\[(.*?)\]\]',lambda m:slots[m.group(1)],text)


def validate_answer(answer,results,contexts,scope,hypotheses,intent):
    problems=[]
    ids={c['id'] for c in contexts}
    if {c.context_id for c in answer.context_review}!=ids:problems.append('Review every retrieved owner context note: '+', '.join(sorted(ids)))
    if answer.next_step_kind=='action':
        if not answer.primary_driver or answer.primary_driver.level=='unverified_possibility' or answer.confidence in ['possible explanation','insufficient evidence']:
            problems.append('An action requires a supported primary diagnosis; otherwise recommend investigation.')
    if intent=='analysis':
        if not hypotheses:problems.append('Retain the hypotheses tested during investigation; qualify unsupported explanations as inconclusive.')
        # Alternatives may be supported contributors or inconclusive, not necessarily contradicted.
        # The semantic audit checks whether the evidence justifies the confidence and mechanism.
    for h in hypotheses:
        if h.status in ['supported','contradicted'] and not h.evidence:problems.append('A tested hypothesis needs evidence: '+h.explanation)
        for ref in h.evidence:
            try:reference_value(results,ref.model_dump())
            except QueryBlocked as exc:problems.append(f'{exc}: hypothesis {h.explanation!r}, reference {ref.model_dump()}')
    rendered={}
    for s in statements(answer):
        if not set(s.context_ids)<=ids:problems.append('Unknown context reference: '+s.text)
        if s.level!='unverified_possibility' and not (s.evidence or s.context_ids):problems.append('Observed facts and interpretations need evidence: '+s.text)
        try:rendered[id(s)]=render_statement(s,results,scope)
        except QueryBlocked as exc:problems.append(f'{exc}; statement references: {[r.model_dump() for r in s.evidence]}')
    for index in answer.table_results:
        if index<0 or index>=len(results):problems.append(f'Table result index {index} does not exist. Use zero-based result_index, not a row value.')
    visual=answer.visual.model_dump()
    try:validate_chart(results,visual)
    except QueryBlocked as exc:problems.append(str(exc))
    if problems:raise QueryBlocked('\n'.join(problems[:8]))
    if visual['kind']=='pie':
        rows=results[visual['result']]['rows']
        if len({str(r[visual['x']]) for r in rows})>6:raise QueryBlocked('Use a bar for more than six composition categories.')
        # The semantic auditor additionally checks staff/date/category scope.
        total=sum(r[visual['y']] for r in rows)
        candidates=[v for i,res in enumerate(results) if i!=visual['result'] for row in res['rows'] for key,v in row.items()
                    if type(v) in (int,float) and any(word in key.lower() for word in ['revenue','total','amount','value'])]
        if not any(math.isclose(total,v,rel_tol=1e-8,abs_tol=.005) for v in candidates):
            raise QueryBlocked('Pie composition requires a separately retrieved matching scoped total.')
    return rendered
