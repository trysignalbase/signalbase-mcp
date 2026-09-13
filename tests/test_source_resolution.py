import asyncio

import pytest
import entry


def test_only_apply_actions_are_followed():
    body = '<a href="https://jobs.lever.co/wrong/id">Related job</a><a href="/job/go/123/">Apply for this position</a>'
    assert entry._wf_application_links(body, 'https://www.workingnomads.com/jobs/example-123') == ['https://www.workingnomads.com/job/go/123/']
    mixed = '<main><a href="/job/go/123/">Apply</a></main><aside><a href="https://jobs.lever.co/other-company/id">Apply</a></aside>'
    assert len(entry._wf_application_links(mixed, 'https://www.workingnomads.com/jobs/example-123')) == 2


@pytest.mark.parametrize('url', [
    'http://jobs.lever.co/acme/id', 'https://jobs.lever.co:8443/acme/id',
    'https://jobs.lever.co.evil.example/acme/id', 'https://user:secret@jobs.lever.co/acme/id',
    'https://127.0.0.1/job/1', 'https://169.254.169.254/latest/meta-data',
    'https://www.workingnomads.com/jobs/test?api_key=secret',
    'https://www.workingnomads.com/jobs/test?api%5Fkey=secret',
])
def test_nonpublic_or_untrusted_targets_are_refused(url):
    assert not entry._wf_source_url_allowed(url)


def test_aggregator_apply_redirect_verifies_same_employer_posting(monkeypatch):
    urls = []
    async def page(url):
        urls.append(url)
        if '/job/go/' in url:
            return 302, None, 'https://jobs.ashbyhq.com/secfix/job-id'
        return 200, '<a href="/job/go/123/">Apply for this position</a>', None
    async def public(url):
        urls.append(url)
        return 200, {'jobs': [{'title': 'Product Support Specialist', 'jobUrl': 'https://jobs.ashbyhq.com/secfix/job-id', 'applyUrl': 'https://jobs.ashbyhq.com/secfix/job-id/application'}]}
    monkeypatch.setattr(entry, '_wf_public_page', page)
    monkeypatch.setattr(entry, '_wf_public_json', public)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://www.workingnomads.com/jobs/example-123', 'title': 'Product Support Specialist'}))
    assert result['source_verified_open'] is True
    assert result['source_verification']['resolved_url'] == 'https://jobs.ashbyhq.com/secfix/job-id'
    assert len(result['source_verification']['source_chain']) == 2
    assert len(urls) == 3


def test_redirect_to_private_host_is_never_fetched(monkeypatch):
    calls = []
    async def page(url):
        calls.append(url)
        return 302, None, 'https://127.0.0.1/admin'
    monkeypatch.setattr(entry, '_wf_public_page', page)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://www.workingnomads.com/job/go/123/', 'title': 'Engineer'}))
    assert result['source_verified_open'] is None
    assert len(calls) == 1


def test_multiple_application_targets_are_not_guessed(monkeypatch):
    async def page(url):
        return 200, '<a href="https://jobs.lever.co/a/1">Apply</a><a href="https://jobs.lever.co/b/2">Apply</a>', None
    monkeypatch.setattr(entry, '_wf_public_page', page)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://feeny.ai/job/1', 'title': 'Engineer'}))
    assert result['source_verified_open'] is None
    assert result['source_verification']['status'] == 'ambiguous_application_links'


def test_live_verification_requires_two_distinct_jobs_when_requested():
    company = entry._wf_company_results([{'id':'1','companyId':'a','title':'Engineer'},{'id':'2','companyId':'a','title':'Designer'}], {})[0]
    company['postings'][0]['source_verified_open'] = True
    result = entry._wf_finalize_company(company, {'required_evidence':['verified_live_vacancy'],'min_distinct_role_titles':2})
    assert result['unverified_requirements'][0]['requirement'] == 'verified_live_vacancy'


def test_screening_reports_intermediaries_and_conflicting_funding():
    row = {'companyName':'Widget Works', 'companyDescription':'A recruiting marketplace that connects candidates with employers.', 'matchedFunding':[{'signalId':'f','sources':[{'title':'Other Company raises $10M','url':'https://news.example/f'}]}]}
    codes = {flag['code'] for flag in entry._wf_screen_row(row, {})}
    assert codes == {'possible_intermediary', 'funding_subject_conflict'}


def test_headcount_conflict_requires_an_explicit_numeric_claim():
    assert entry._wf_screen_row({'companyEmployeeCount':5, 'companyDescription':'A global leader with customers worldwide.'}, {}) == []
    flags = entry._wf_screen_row({'companyEmployeeCount':5, 'companyDescription':'We have over 4,000 employees worldwide.'}, {})
    assert flags[0]['code'] == 'headcount_conflict'
    assert entry._wf_screen_row({'companyEmployeeCount':5, 'companyDescription':'Our software serves teams of 4,000 people around the world.'}, {}) == []
    assert entry._wf_screen_row({'companyEmployeeCount':5, 'companyDescription':'We have 4,000 people using our app every day.'}, {}) == []
    assert entry._wf_screen_row({'companyEmployeeCount':5, 'companyDescription':'We have never said we have 4,000 employees.'}, {}) == []


def test_geographic_prefix_does_not_make_a_funding_subject_conflict():
    row={'companyName':'Widget Works','matchedFunding':[{'sources':[{'title':'Berlin-based Widget Works raises $10M'}]}]}
    assert entry._wf_screen_row(row,{}) == []


def test_http_timeout_without_usage_marks_credit_cost_unknown(monkeypatch):
    async def api(endpoint, params, key):
        return {'error':True,'status':504,'body':{'error':'Gateway timeout'}}
    monkeypatch.setattr(entry,'_call_api',api)
    ledger={'api_calls':0,'credits_used':0,'max_api_calls':12}
    with pytest.raises(entry.WorkflowError):
        asyncio.run(entry._wf_fetch('/signals/hiring',{},'key',ledger))
    assert ledger['credits_known'] is False and ledger['requests_with_unknown_cost'] == 1


def test_paid_success_without_usage_marks_credit_cost_unknown(monkeypatch):
    async def api(endpoint, params, key):
        return {'data': [], 'pagination': {'totalCount': 0, 'hasNextPage': False}}
    monkeypatch.setattr(entry, '_call_api', api)
    ledger = {'api_calls': 0, 'credits_used': 0, 'max_api_calls': 12}
    asyncio.run(entry._wf_fetch('/signals/hiring', {}, 'key', ledger))
    assert ledger['credits_used'] == 0
    assert ledger['credits_known'] is False
    assert ledger['requests_with_unknown_cost'] == 1


def test_sales_engineer_is_flagged_only_for_software_specific_request():
    row = {'title':'Founding Sales Engineer'}
    assert entry._wf_screen_row(row, {'role':'software engineer'})[0]['code'] == 'adjacent_role'
    assert entry._wf_screen_row(row, {'role':'engineers'}) == []


def test_public_ats_requests_use_runtime_supported_manual_redirects(monkeypatch):
    from types import SimpleNamespace
    options = []
    async def fetch(url, opts):
        options.append(opts)
        return SimpleNamespace(status=302, ok=False)
    monkeypatch.setattr(entry, 'fetch', fetch)
    assert asyncio.run(entry._wf_public_json('https://api.lever.co/v0/postings/acme/a')) == (302, None)
    assert options[0]['redirect'] == 'manual'
    assert 'Authorization' not in options[0]['headers']


def test_screening_demotes_without_discarding_returned_rows(monkeypatch):
    import json
    async def api(endpoint, params, key):
        return {'data':[
            {'id':'bad','companyId':'a','companyName':'Agency','companyDescription':'A recruiting marketplace.'},
            {'id':'good','companyId':'b','companyName':'Employer','title':'Engineer'},
        ],'pagination':{'totalCount':2,'hasNextPage':False},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    rpc=asyncio.run(entry._handle_jsonrpc({'id':1,'method':'tools/call','params':{'name':'find_hiring_companies','arguments':{}}}, 'test','hr'))
    payload=json.loads(rpc['result']['content'][0]['text'])
    assert [c['company'] for c in payload['companies']] == ['Employer','Agency']
    assert payload['companies'][1]['match_status'] == 'needs_review'
    assert payload['coverage']['rows_scanned'] == 2
    assert payload['screening_summary']['companies_needing_review'] == 1


@pytest.mark.parametrize('canonical,expected', [('https://careers.acme.com/jobs/123',True),('https://acme.com.evil.example/jobs/123',None)])
def test_greenhouse_custom_career_subdomain_is_owned(monkeypatch,canonical,expected):
    async def public(url):
        return 200, {'id':123,'internal_job_id':456,'title':'Software Engineer','company_name':'Acme','absolute_url':canonical}
    monkeypatch.setattr(entry,'_wf_public_json',public)
    result=asyncio.run(entry._wf_verify_live_posting({'url':'https://boards.greenhouse.io/acme/jobs/123','title':'Software Engineer','company_name':'Acme','company_domain':'acme.com'}))
    assert result['source_verified_open'] is expected
