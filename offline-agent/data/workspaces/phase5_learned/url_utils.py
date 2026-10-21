def parse_query(query_str: str) -> dict:
    query_str = query_str.lstrip('?') if '?' in query_str else query_str
    params = {}
    if query_str:
        for pair in query_str.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                if k and v:
                    params[k] = v
    return params


def build_query(params: dict) -> str:
    sorted_params = sorted(params.items())
    return '&'.join(f'{k}={v}' for k, v in sorted_params)