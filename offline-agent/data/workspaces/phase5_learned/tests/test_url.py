import pytest

from url_utils import parse_query, build_query

@pytest.fixture
def query_str():
    return 'param1=value1&param2=value2'

@pytest.fixture
def params():
    return {'b': '2', 'a': '1'}


def test_parse_query_standard_params(query_str):
    assert parse_query(query_str) == {'param1': 'value1', 'param2': 'value2'}


def test_parse_query_leading_question_mark(query_str):
    assert parse_query('?param1=value1&param2=value2') == {'param1': 'value1', 'param2': 'value2'}


def test_parse_query_empty_string(query_str):
    assert parse_query('') == {}


def test_parse_query_multiple_pairs(query_str):
    assert parse_query('param1=value1&param2=value2&param3=value3') == {'param1': 'value1', 'param2': 'value2', 'param3': 'value3'}


def test_build_query_sorting(params):
    assert build_query(params) == 'a=1&b=2'


def test_build_query_empty_dict(params):
    assert build_query({}) == ''


def test_build_query_basic_dict(params):
    assert build_query({'param1': 'value1', 'param2': 'value2'}) == 'param1=value1&param2=value2'