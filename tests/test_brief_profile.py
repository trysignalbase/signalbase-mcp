import asyncio
import copy
import json
import hashlib

import pytest
import entry


@pytest.mark.parametrize('profile,tools_hash,init_hash', [
    ('classic','9f52cafbb4e6dd7dcbdba1afbbca34ab1c996eb77290a931ccf14af0031c41fe','07aec7e538e8495928f69813f00517dc8a28f58aab89fc98ecc358dd4ca7fb38'),
    ('hr','8b8cfb761344adb347b244c68984e0ec0566407a9d79d89b8cb6beaf0b372f62','f67085e03183d79e8c932b59c92e5de213f01aab8342d471f3630c52e52c04fe'),
])
def test_prebrief_discovery_contract_is_byte_equivalent(profile,tools_hash,init_hash):
    # Recorded from approved pre-change commit71bca59; re-recorded for 1.2.0 (classic exposes
    # hiring `description` + funding `date_basis` default, shared prop text on hr). Not current expectations.
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    assert digest(entry._tools_for_profile(profile))==tools_hash
    assert digest(asyncio.run(entry._handle_jsonrpc({'id':1,'method':'initialize'},'key',profile)))==init_hash


def rows():
    return [
        {'companyId':'a','id':'good','companyName':'Alpha','title':'Software Engineer','jobUrl':'https://jobs.ashbyhq.com/a/good','datePosted':'2026-09-10'},
        {'companyId':'a','id':'old','companyName':'Alpha','title':'Data Engineer','jobUrl':'https://jobs.ashbyhq.com/a/old','datePosted':'2026-09-10'},
    ]


def mixed_company(args):
    company=entry._wf_company_results(rows(),args)[0]
    for posting,date in zip(company['postings'],['2026-09-10','2026-07-01']):
        posting.update(source_verified_open=True,source_verification={'status':'open','published_at':date,'canonical_url':posting['url']})
    return company


def test_brief_is_opt_in_and_does_not_mutate_discovery():
    before=copy.deepcopy(entry._tools_for_profile('hr'))
    tools=entry._tools_for_profile('hr_brief')
    assert len(tools)==4
    assert len(json.dumps(tools)) < len(json.dumps(before))*.45
    assert entry._tools_for_profile('hr')==before
    assert len(entry._tools_for_profile('classic'))==6


def test_recruiting_profile_is_versioned_and_text_only(monkeypatch):
    calls=[]
    async def api(endpoint,params,key):
        calls.append((endpoint,params))
        return {'data':[{'companyId':'a','companyName':'Alpha','companyWebsite':'https://alpha.example','postingCount':2,'distinctRoleTitles':2,
                         'postings':[{'id':'j','role':'Engineer','url':'https://example.org/j','evidence_excerpt':'Engineer evidence'}]}],
                'pagination':{'nextCursor':'next-company','hasNextPage':True},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    init=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'initialize'},'key','hr_recruiting'))
    assert init['result']['serverInfo']['version']=='2.1.0'
    hiring=next(tool for tool in entry._tools_for_profile('hr_recruiting') if tool['name']=='find_hiring_companies')
    assert 'cursor' in hiring['inputSchema']['properties'] and 'page' not in hiring['inputSchema']['properties']
    response=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{'name':'find_hiring_companies','arguments':{'request':'Find engineers','role':'engineers','verify_live':False}}},'key','hr_recruiting'))
    assert 'structuredContent' not in response['result']
    payload=json.loads(response['result']['content'][0]['text'])
    assert payload['summary']['returned_companies']==1
    assert payload['prospects'][0]['postings'][0]['id']=='j'
    assert payload['prospects'][0]['company_first_evidence']['distinct_role_titles_in_filtered_cohort']==2
    assert payload['coverage']['next_cursor']=='next-company'
    assert calls[0][0]=='/recruiting/hiring-companies'
    assert calls[0][1]['companies_limit']==10 and calls[0][1]['postings_per_company']==3
    assert payload['field_notes']['coverage'].startswith('index/query')


def test_recruiting_projection_merges_duplicate_funding_evidence():
    card={'company':'Alpha','postings':[],'qualification':'matches_indexed_filters','match_status':'supported_indexed',
          'funding':[{'signalId':'f1','roundType':'seed','amount':12000000,'currency':'USD','sources':[{'url':'https://alpha.example/funding'}]}],
          'funding_review':[{'signal_id':'f1','source_identity_status':'supported_by_company_domain','evidence_status':'supported'}]}
    projected=entry._lean_company_card(card)
    assert len(projected['funding'])==1
    assert projected['funding'][0]['id']=='f1'
    assert projected['funding'][0]['source_identity']=='supported_by_company_domain'
    assert 'funding_review' not in projected


def test_recruiting_projection_keeps_secondary_trigger_attribution():
    candidate={
        'record_id':'primary','signal':'seed','triggers':[
            {'record_id':'primary','signal':'seed'},
            {'record_id':'secondary','signal':'series_a','signal_date':'2026-09-01','role':None,
             'stored_dates':{'announcedDate':'2026-09-01'},
             'source_evidence':[{'url':'https://news.example/f','title':'A raises'}],
             'funding':{'round':'series a','amount':12000000,'currency':'USD','investors':[{'name':'VC'}],
                        'verification_status':'verified','source_identity_status':'supported_by_source_title'}},
        ],
    }
    projected=entry._lean_candidate(candidate)
    [trigger]=projected['other_triggers']
    assert trigger['stored_dates']['announcedDate']=='2026-09-01'
    assert trigger['source_evidence'][0]['title']=='A raises'
    assert trigger['funding']['amount']==12000000 and trigger['funding']['investors'][0]['name']=='VC'


def test_recruiting_uses_nonfiltering_office_terms_and_recognizes_excerpt(monkeypatch):
    calls=[]
    async def api(endpoint,params,key):
        calls.append((endpoint,params))
        return {'data':[{'companyId':'a','companyName':'Alpha','companyWebsite':'https://alpha.example',
                         'postings':[{'id':'j','role':'Engineer','url':'https://example.org/j',
                                      'evidence_excerpt':'Our office in Poland is hiring now.'}]}],
                'pagination':{'nextCursor':None,'hasNextPage':False},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    response=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{
        'name':'find_hiring_companies','arguments':{
            'request':'Companies with offices in Poland hiring now',
            'required_evidence':['office_presence'],'office_locations':['Poland'],'verify_live':False,
        }}},'key','hr_recruiting'))
    payload=json.loads(response['result']['content'][0]['text'])
    assert '"Poland office"' in calls[0][1]['evidence_terms']
    assert payload['prospects'][0]['supported_claims'][0]['requirement']=='office_presence'


def test_recruiting_terminal_cursor_page_is_not_globally_complete(monkeypatch):
    async def api(endpoint,params,key):
        return {'data':[],'pagination':{'nextCursor':None,'hasNextPage':False},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    response=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{
        'name':'find_hiring_companies','arguments':{
            'request':'Continue companies','cursor':'opaque-next','verify_live':False,
        }}},'key','hr_recruiting'))
    payload=json.loads(response['result']['content'][0]['text'])
    assert payload['query_status']=='partial'
    assert payload['coverage']['query_exhausted_after_cursor'] is True
    assert payload['coverage']['complete_from_first_page'] is False


def test_recruiting_projection_preserves_secondary_trigger_attribution():
    candidate={'record_id':'primary','triggers':[
        {'record_id':'primary','signal':'seed','signal_date':'2026-09-01'},
        {'record_id':'second','signal':'series_a','signal_date':'2026-09-02','role':'VP Engineering',
         'stored_dates':{'occurredAt':'2026-09-02'},
         'source_evidence':[{'url':'https://source.example','title':'A raises'}],
         'funding':{'round':'series a','amount':12000000,'currency':'USD','investors':[{'name':'Example VC'}],'verification_status':'verified'}}]}
    projected=entry._lean_candidate(candidate)
    [trigger]=projected['other_triggers']
    assert trigger['funding']['amount']==12000000
    assert trigger['funding']['investors'][0]['name']=='Example VC'
    assert trigger['source_evidence'][0]['title']=='A raises'


def test_brief_keeps_good_posting_and_isolates_stale_posting():
    args={'posted_within_days':14,'as_of':'2026-09-12','required_evidence':['verified_live_vacancy']}
    result=entry._wf_finalize_company(mixed_company(args),args,brief=True)
    assert result['qualification']=='matches_requested_criteria'
    assert result['eligible_posting_ids']==['good']
    assert result['posting_review'][0]['posting_id']=='old'
    old=entry._wf_finalize_company(mixed_company(args),args)
    assert old['match_status']=='needs_review'  # existing default contract frozen


def test_multiple_live_roles_require_multiple_eligible_not_stale_roles():
    args={'posted_within_days':14,'as_of':'2026-09-12','required_evidence':['verified_live_vacancy'],'min_distinct_role_titles':2}
    result=entry._wf_finalize_company(mixed_company(args),args,brief=True)
    assert result['qualification']!='matches_requested_criteria'
    assert any(c['requirement']=='verified_live_vacancy' for c in result['unverified_requirements'])


def test_company_identity_conflict_is_never_waived_by_good_posting():
    args={}
    company=mixed_company(args)
    company['_screening']=[{'code':'headcount_conflict','status':'needs_review'}]
    result=entry._wf_finalize_company(company,args,brief=True)
    assert result['match_status']=='needs_review'


def test_brief_verification_selection_is_fair_and_skips_unsupported_urls():
    companies=[{'company':'A','postings':[{'id':str(i),'url':f'https://www.linkedin.com/jobs/{i}'} for i in range(20)]+[{'id':'ats-a','url':'https://jobs.ashbyhq.com/a/11111111-1111-4111-8111-111111111111'}]},
               {'company':'B','postings':[{'id':'ats-b','url':'https://jobs.ashbyhq.com/b/22222222-2222-4222-8222-222222222222'}]}]
    selected=entry._wf_verification_candidates(companies,2)
    assert [p['id'] for _,p in selected]==['ats-a','ats-b']


def test_brief_summary_is_successful_even_with_one_review_candidate(monkeypatch):
    async def api(endpoint,params,key):
        return {'data':[{'companyId':'a','id':'a','companyName':'Good','title':'Engineer','jobUrl':'https://example.org/a'},
                        {'companyId':'b','id':'b','companyName':'Check','title':'Engineer','descriptionText':'This job is at AnotherCorp.'}],
                'pagination':{'totalCount':2},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    result=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{'name':'find_hiring_companies','arguments':{'request':'Find engineers','role':'engineers','verify_live':False}}},'key','hr_brief'))
    p=json.loads(result['result']['content'][0]['text'])
    assert p['execution_status']=='succeeded'
    assert p['summary']['returned_companies']==2
    assert len(p['prospects'])==1 and len(p['needs_review'])==1
    assert p['request']=='Find engineers'
    assert result['result']['structuredContent']==p
    assert '\n' not in result['result']['content'][0]['text']
    assert '": ' not in result['result']['content'][0]['text']


def test_brief_unknown_or_raw_tool_is_rejected_before_io(monkeypatch):
    async def api(*args):raise AssertionError('No I/O')
    monkeypatch.setattr(entry,'_call_api',api)
    r=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{'name':'search_hiring_signals','arguments':{}}},'key','hr_brief'))
    assert r.get('error') or r.get('result',{}).get('isError')


def test_brief_budget_reserves_timed_out_paid_calls(monkeypatch):
    calls=[]
    async def api(*args):
        calls.append(args)
        raise TimeoutError()
    monkeypatch.setattr(entry,'_call_api',api)
    ledger={'api_calls':0,'credits_used':0,'max_api_calls':10,'_credit_limit':1}
    async def run():
        with pytest.raises(entry.WorkflowError,match='TimeoutError'):
            await entry._wf_fetch('/signals/hiring',{},'key',ledger)
        with pytest.raises(entry.WorkflowError,match='Credit budget'):
            await entry._wf_fetch('/signals/hiring',{},'key',ledger)
    asyncio.run(run())
    assert len(calls)==1 and ledger['credits_reserved_unknown']==1


def test_brief_budget_allows_free_counts_and_known_zero_charge(monkeypatch):
    async def api(*args):return {'data':[],'pagination':{},'meta':{'creditsUsed':0}}
    monkeypatch.setattr(entry,'_call_api',api)
    ledger={'api_calls':0,'credits_used':0,'max_api_calls':10,'_credit_limit':0}
    asyncio.run(entry._wf_fetch('/signals/hiring',{'count':True},'key',ledger))
    assert ledger['credits_used']==0 and ledger['api_calls']==1


def test_brief_budget_reserves_success_with_unknown_credit_cost(monkeypatch):
    async def api(*args):return {'data':[],'pagination':{}}
    monkeypatch.setattr(entry,'_call_api',api)
    ledger={'api_calls':0,'credits_used':0,'max_api_calls':10,'_credit_limit':1}
    asyncio.run(entry._wf_fetch('/signals/hiring',{},'key',ledger))
    assert ledger['credits_known'] is False
    assert ledger['requests_with_unknown_cost']==1
    assert ledger['credits_reserved_unknown']==1


def test_discarded_posting_cannot_supply_office_claim():
    args={'posted_within_days':14,'as_of':'2026-09-12','required_evidence':['office_presence']}
    company=mixed_company(args)
    company['_source_claims']={'office_presence':{'requirement':'office_presence','status':'supported_source_text','posting_id':'old','quote':'Our Warsaw office'}}
    result=entry._wf_finalize_company(company,args,brief=True)
    assert result['match_status']=='partial_evidence'
    assert not any(c.get('requirement')=='office_presence' for c in result['criteria'])


def test_later_eligible_posting_recovers_its_own_office_evidence():
    args={'office_locations':['Poland'],'required_evidence':['office_presence'],'posted_within_days':14,'as_of':'2026-09-12'}
    evidence_rows=[{'companyId':'a','id':'old','title':'Data Engineer','descriptionText':'Work from our Warsaw office.'},
                   {'companyId':'a','id':'good','title':'Software Engineer','descriptionText':'This role is based in our Warsaw office.'}]
    company=entry._wf_company_results(evidence_rows,args,brief=True)[0]
    company['postings'][0].update(source_verified_open=True,source_verification={'published_at':'2026-07-01'})
    result=entry._wf_finalize_company(company,args,brief=True)
    assert result['match_status']=='supported_with_source_text'
    claim=next(c for c in result['criteria'] if c['requirement']=='office_presence')
    assert claim['posting_id']=='good'


def test_brief_hq_alternatives_are_executable_brief_tools():
    r=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{'name':'find_hiring_companies','arguments':{'request':'Bay Area Seed engineers','role':'engineers','company_hq_city':'San Francisco Bay Area','funding_rounds':['Seed']}}},'key','hr_brief'))
    p=r['result']['structuredContent']
    alternative=p['suggested_queries'][0]
    assert alternative['tool']=='find_hiring_companies'
    descriptor=next(t for t in entry._brief_tools() if t['name']==alternative['tool'])
    entry._validate_tool_arguments(descriptor,alternative['arguments'])
    assert alternative['arguments']['funding_rounds']==['Seed']
    assert alternative['arguments']['request']=='Bay Area Seed engineers'


def test_eligible_ats_office_claim_survives_an_old_indexed_claim(monkeypatch):
    args={'required_evidence':['office_presence'],'office_locations':['Poland'],'verify_live':True,'posted_within_days':14,'as_of':'2026-09-12'}
    rr=rows()
    rr[0].update(id='old',descriptionText='Our office is in Warsaw.',jobUrl='https://jobs.ashbyhq.com/a/11111111-1111-4111-8111-111111111111')
    rr[1].update(id='good',jobUrl='https://jobs.ashbyhq.com/a/22222222-2222-4222-8222-222222222222')
    companies=entry._wf_company_results(rr,args,brief=True)
    async def verify(posting,cache):return {'source_verified_open':True,'source_verification':{'status':'open','offices':['Warsaw'],'published_at':'2026-07-01' if posting['id']=='old' else '2026-09-10'}}
    monkeypatch.setattr(entry,'_wf_verify_live_posting',verify)
    asyncio.run(entry._wf_verify_companies(companies,args,{'_brief':True}))
    result=entry._wf_finalize_company(companies[0],args,brief=True)
    claim=next(c for c in result['criteria'] if c['requirement']=='office_presence')
    assert claim['posting_id']=='good' and claim['status']=='supported_source_verified'


def test_brief_retains_identity_conflict_evidence_and_employer_url():
    company=mixed_company({})
    company['postings'][0]['source_verification']={'status':'identity_conflict','reason':'source_title_differs','source_title':'Sales Engineer','resolved_url':'https://jobs.ashbyhq.com/a/source','checked_at':'2026-09-12'}
    card=entry._brief_company_card(entry._wf_finalize_company(company,{},brief=True))
    source=next(p['source'] for p in card['postings'] if p['id']=='good')
    assert source['source_title']=='Sales Engineer'
    assert source['resolved_url']=='https://jobs.ashbyhq.com/a/source'
