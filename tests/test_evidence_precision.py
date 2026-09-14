"""Adversarial evidence cases: a successful request must not manufacture proof."""
import asyncio

import pytest
import entry


@pytest.mark.parametrize('text,requirement', [
    ('You will not be our first sales hire.', 'first_hire'),
    ("You will be the right-hand to the CEO.", 'founder_right_hand'),
    ("You will not be our founder's right hand.", 'founder_right_hand'),
    ('We are not opening a new office in Poland.', 'office_opening'),
    ('We are no longer scaling our team.', 'company_scaling'),
    ('We have no expansion budget.', 'expansion_budget'),
    ('Our founder leads sales at another company.', 'founder_led_sales'),
    ('We stopped scaling our team last year.', 'company_scaling'),
    ('Experience opening a new office in Poland is required.', 'office_opening'),
    ('Our first employee joined in 2015 and leads the team.', 'first_hire'),
    ('You will be mentored by our first employee.', 'first_hire'),
    ('We are hiring a designer to work alongside our first employee.', 'first_hire'),
    ('Our founder leads sales? No, our sales team handles that.', 'founder_led_sales'),
])
def test_unsupported_or_negated_claim_is_not_positive_evidence(text, requirement):
    assert entry._wf_source_claims({'descriptionText': text, 'jobUrl': 'https://example.org/job/1'}, [requirement], {}) == {}


def test_first_functional_hire_is_not_first_regional_employee():
    row = {'descriptionText': 'You will be our first Revenue Operations hire in London.', 'location': 'London'}
    assert entry._wf_source_claims(row, ['first_hire'], {'first_hire_scope': 'regional', 'job_locations': ['UK']}) == {}
    assert entry._wf_source_claims({'descriptionText':'You will be our first employee based in Poland.'}, ['first_hire'], {'first_hire_scope':'company'}) == {}
    assert entry._wf_source_claims({'descriptionText':'You will be our first employee in engineering, working remotely from Poland.'}, ['first_hire'], {'first_hire_scope':'regional','job_locations':['Poland']}) == {}


def test_positive_first_regional_hire_keeps_exact_evidence():
    row = {'descriptionText': 'You will be our first employee in Poland.', 'location': 'Warsaw', 'jobUrl': 'https://example.org/job/1'}
    claim = entry._wf_source_claims(row, ['first_hire'], {'first_hire_scope': 'regional', 'job_locations': ['Poland']})['first_hire']
    assert claim['scope'] == 'regional'
    assert claim['quote'] == row['descriptionText']


@pytest.mark.parametrize('body', [{}, {'error': 'not found'}, {'id': 'different', 'text': 'Engineer', 'hostedUrl': 'https://jobs.lever.co/acme/different'}])
def test_invalid_ats_object_does_not_verify_a_job(monkeypatch, body):
    async def public(url):
        return 200, body
    monkeypatch.setattr(entry, '_wf_public_json', public)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://jobs.lever.co/acme/abc', 'title': 'Engineer'}))
    assert result['source_verified_open'] is None


def test_matching_ats_id_with_wrong_title_is_not_verified(monkeypatch):
    async def public(url):
        return 200, {'id': 'abc', 'text': 'Account Executive', 'hostedUrl': 'https://jobs.lever.co/acme/abc'}
    monkeypatch.setattr(entry, '_wf_public_json', public)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://jobs.lever.co/acme/abc', 'title': 'Software Engineer'}))
    assert result['source_verified_open'] is None


def test_valid_ats_job_with_matching_title_is_verified(monkeypatch):
    async def public(url):
        return 200, {'id': 'abc', 'text': 'Software Engineer', 'hostedUrl': 'https://jobs.lever.co/acme/abc', 'applyUrl': 'https://jobs.lever.co/acme/abc/apply'}
    monkeypatch.setattr(entry, '_wf_public_json', public)
    result = asyncio.run(entry._wf_verify_live_posting({'url': 'https://jobs.lever.co/acme/abc', 'title': 'Software Engineer'}))
    assert result['source_verified_open'] is True
