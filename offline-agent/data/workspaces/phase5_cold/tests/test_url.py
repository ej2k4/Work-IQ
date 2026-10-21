import pytest
from url_utils import parse_query, build_query


def test_parse_query_standard_params():
    query_str = 'param1=value1&param2=value2'
    expected = {'param1': 'value1', 'param2': 'value2'}
    assert parse_query(query_str) == expected


def test_parse_query_leading_question_mark():
    query_str = '?param1=value1&param2=value2'
    expected = {'param1': 'value1', 'param2': 'value2'}
    assert parse_query(query_str) == expected


def test_parse_query_empty_string():
    query_str = ''
    expected = {}
    assert parse_query(query_str) == expected


def test_parse_query_multiple_pairs():
    query_str = 'param1=value1&param2=value2&param3=value3'
    expected = {'param1': 'value1', 'param2': 'value2', 'param3': 'value3'}
    assert parse_query(query_str) == expected


def test_build_query_standard_dict():
    params = {'param1': 'value1', 'param2': 'value2'}
    expected = 'param1=value1&param2=value2'
    assert build_query(params) == expected


def test_build_query_empty_dict():
    params = {}
    expected = ''
    assert build_query(params) == expected


def test_build_query_basic_dict():
    params = {'param3': 'value3', 'param1': 'value1', 'param2': 'value2'}
    expected = 'param1=value1&param2=value2&param3=value3'
    assert build_query(params) == expected
