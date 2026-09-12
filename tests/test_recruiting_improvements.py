import asyncio
import json

import pytest
import entry


def test_software_scope_survives_raw_and_workflow_arguments():
    raw,_,_=entry._prepare_tool_args({'role':'engineers','role_scope':'software'},'search_hiring_signals','hr')
    assert raw['role_scope']=='software' and raw['departments']=='engineering'
    assert entry._wf_hiring_params({'role':'engineers','role_scope':'software'})['role_scope']=='software'
    assert 'role_scope' not in entry._wf_hiring_params({'role':'engineers'})
def test_appointment_workflow_uses_people_not_hiring_endpoint(monkeypatch):
    calls=[]
    async def api(endpoint,params,key):
        calls.append((endpoint,params))
        return {'success':True,'data':[{'personName':'A Person','companyName':'Consumer Brand','newRole':'CFO','occurredAt':'2026-09-11','takenFrom':'https://example.org/announcement'}],'pagination':{'totalCount':1},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    result=asyncio.run(entry._run_hr_workflow('find_recent_appointments',{'role':'cfo','sector':'fmcg','as_of':'2026-09-12T00:00:00Z'},'key'))
    assert calls[0][0]=='/signals/job-changes' and calls[0][1]['positions']=='cfo'
    assert result['appointments'][0]['person']=='A Person'
    assert result['appointments'][0]['start_date'] is None
    assert result['usage']['credits_used']==1


def test_workflow_to_api_keeps_multiplicity_dates_and_hq(monkeypatch):
    calls=[]
    async def api(endpoint,params,key):
        calls.append(params)
        return {'success':True,'data':[],'pagination':{'totalCount':0},'meta':{'creditsUsed':1}}
    monkeypatch.setattr(entry,'_call_api',api)
    result=asyncio.run(entry._run_hr_workflow('find_hiring_companies',{'role':'engineers','company_countries':['United States'],'headcount_min':11,'headcount_max':50,'min_distinct_role_titles':2,'posted_from':'2026-01-01','posted_to':'2026-04-30','required_evidence':['verified_live_vacancy'],'as_of':'2026-09-12T00:00:00Z'},'key'))
    assert calls[0]['min_distinct_titles']==2 and calls[0]['team_size']=='11-50'
    assert calls[0]['dateFrom']=='2026-01-01' and calls[0]['dateTo']=='2026-04-30'
    assert calls[0]['company_countries']=='United States' and 'job_locations' not in calls[0]
    assert result['unverified_requirements'][0]['requirement']=='verified_live_vacancy'


@pytest.mark.parametrize('arguments', [{'role':'cfo','sector':'bad'}, {'role':'cfo','appointed_within_days':-1}, {'role':'cfo','company_countries':['US']}])
def test_invalid_appointment_arguments_make_no_calls(monkeypatch,arguments):
    async def api(*args):raise AssertionError('No paid I/O')
    monkeypatch.setattr(entry,'_call_api',api)
    with pytest.raises((entry.WorkflowError,ValueError)):
        asyncio.run(entry._run_hr_workflow('find_recent_appointments',arguments,'key'))


def test_client_service_duties_do_not_make_an_employer_a_recruiter():
    row = {'companyName':'Supio','companyDescription':'Supio is a legal AI product company.', 'descriptionText':'Serve as the primary point of contact for our clients, ensuring they achieve maximum value from our products and services.'}
    assert not entry._wf_screen_row(row,{})


@pytest.mark.parametrize('text', [
    'We are hiring an engineer on behalf of our client.',
    'We are recruiting a sales manager for one of our clients.',
])
def test_explicit_client_recruitment_still_receives_review(text):
    assert entry._wf_screen_row({'descriptionText':text},{})[0]['code']=='possible_intermediary'


def test_come_to_office_is_explicit_office_presence():
    row={'descriptionText':'Can come to our Warsaw office 1-2 times a week','location':'United States','jobUrl':'https://example.org/job'}
    args={'office_locations':['Poland']}
    claim=entry._wf_source_claims(row,['office_presence'],args)['office_presence']
    assert claim['quote']==row['descriptionText']


@pytest.mark.parametrize('text', ['Cannot come to our Warsaw office.', 'You will visit our clients in Warsaw.', 'Experience opening a Warsaw office is required.'])
def test_visits_do_not_invent_office_presence(text):
    assert not entry._wf_source_claims({'descriptionText':text},['office_presence'],{'office_locations':['Poland']})


def test_office_or_founder_request_can_be_satisfied_by_office_branch():
    args={'required_evidence':['office_presence','founder_origin'],'required_evidence_mode':'any','office_locations':['Poland']}
    row={'companyId':'c','descriptionText':'Can come to our Warsaw office weekly.','location':'Remote'}
    company=entry._wf_finalize_company(entry._wf_company_results([row],args)[0],args)
    assert company['match_status']=='supported_with_source_text'
    assert company['criteria_logic']['required_evidence']=='any'
    assert company['unverified_requirements'][0]['requirement']=='founder_origin'


def test_explicit_different_employer_name_is_flagged():
    row={'companyName':'DevProofs','descriptionText':'About the company\nPlato is a platform for engineering teams. Join Plato as our Founding GTM Engineer.'}
    assert any(f['code']=='employer_name_conflict' for f in entry._wf_screen_row(row,{}))


def test_company_customer_names_do_not_become_employers():
    row={'companyName':'Widget Works','descriptionText':'You will help customers such as Plato and support their teams.'}
    assert not entry._wf_screen_row(row,{})


def test_incompatible_company_self_descriptions_are_reviewed():
    row={'companyName':'Outpost Technologies','companyIndustry':'Defense & Space','companyDescription':'We build defense, space and flight hardware.', 'descriptionText':'About us\nWe are a payments company helping merchants sell globally.'}
    assert any(f['code']=='employer_business_conflict' for f in entry._wf_screen_row(row,{}))


def test_job_skill_alone_does_not_contradict_employer_business():
    row={'companyIndustry':'Defense & Space','companyDescription':'We build defense and flight hardware.','descriptionText':'You will integrate payments for our company website.'}
    assert not entry._wf_screen_row(row,{})


@pytest.mark.parametrize('text', ['Join Us as our next engineer.', 'Join Our Team as an engineer.', 'About us\nIt is a platform for everything.', 'We are hiring an engineer to build software for our clients.', 'We are not hiring on behalf of our client.'])
def test_generic_employer_and_customer_duties_are_not_conflicts(text):
    assert not entry._wf_screen_row({'companyName':'Widget Works','descriptionText':text},{})


@pytest.mark.parametrize('text', ["Visit our client's Warsaw office.", "Come to our partner's Warsaw office.", 'Return to our former Warsaw office.', 'Come to our future Warsaw office.', 'Our office is in Boston.'])
def test_independent_office_geography_and_subject_are_not_substituted(text):
    assert not entry._wf_source_claims({'descriptionText':text,'location':'Boston, United States'}, ['office_presence'], {'office_locations':['Poland'],'job_locations':['United States']})


def test_regional_first_hire_uses_job_not_office_region():
    assert not entry._wf_source_claims({'descriptionText':'You will be our first employee in Poland.'}, ['first_hire'], {'first_hire_scope':'regional','job_locations':['United States'],'office_locations':['Poland']})


def test_or_subgroup_does_not_waive_other_hard_requirements():
    args={'required_evidence':['office_presence','founder_origin','verified_live_vacancy'],'required_evidence_any_of':['office_presence','founder_origin'],'office_locations':['Poland']}
    row={'companyId':'c','descriptionText':'Can come to our Warsaw office weekly.','location':'Remote'}
    company=entry._wf_finalize_company(entry._wf_company_results([row],args)[0],args)
    assert company['match_status']=='partial_evidence'
    assert company['qualification']=='partial'
