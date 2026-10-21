# URL Utils Documentation

## parse_query Function

- **Parameters**:
  - `query_str`: A string representing the query parameters.

- **Return Type**: A dictionary containing the parsed query parameters.

- **Usage Example**:
  ```python
  from url_utils import parse_query

  query_str = 'name=John&age=30&city=New York'
  parsed_query = parse_query(query_str)
  print(parsed_query)  # Output: {'name': 'John', 'age': '30', 'city': 'New York'}
  ```

## build_query Function

- **Parameters**:
  - `params`: A dictionary containing the query parameters.

- **Return Type**: A string representing the query parameters.

- **Usage Example**:
  ```python
  from url_utils import build_query

  params = {'name': 'John', 'age': 30, 'city': 'New York'}
  query_str = build_query(params)
  print(query_str)  # Output: 'name=John&age=30&city=New York'
  ```