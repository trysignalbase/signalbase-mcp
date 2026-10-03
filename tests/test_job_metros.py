import entry


def test_new_york_hq_request_offers_the_job_metro_alternative():
    # The app now filters New York City (and NYC/Manhattan) as a job metro, so
    # an unsupported HQ-city request can offer it as a labelled proxy.
    for city in ("New York", "NYC", "Boston", "London"):
        alternatives = entry._wf_hq_city_alternatives({"company_hq_city": city}, "find_hiring_companies")
        assert any(alt["arguments"].get("job_locations") == [city] for alt in alternatives), city


def test_worker_metros_mirror_the_app():
    for key in ("new york city", "nyc", "manhattan", "washington dc", "munich", "san francisco bay area", "dubai"):
        assert key in entry.JOB_METRO_COUNTRIES
