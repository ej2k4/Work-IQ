def parse_query(query_str: str) -> dict:
    '''
    Parse a query string into a dictionary.

    :param query_str: The query string to parse.
    :return: A dictionary of query parameters.
    '''
    query_str = query_str.lstrip('?') if '?' in query_str else query_str
    params = dict(q.split('=') for q in query_str.split('&') if q)
    return params


def build_query(params: dict) -> str:
    '''
    Build a query string from a dictionary of parameters.

    :param params: A dictionary of query parameters.
    :return: A query string.
    '''
    params = sorted(params.items())
    return '&'.join(f'{k}={v}' for k, v in params)
