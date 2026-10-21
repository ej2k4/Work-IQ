# URL Utils Documentation

## parse_query Function

- **Parameters**:
  - `query_str`: A string representing the query string to be parsed.

- **Return Type**: A dictionary where keys are query parameters and values are their corresponding values.

- **Usage Examples**:
  ```python
  from url_utils import parse_query

  query = parse_query('name=John&age=30&city=New York')
  print(query)  # Output: {'name': 'John', 'age': '30', 'city': 'New York'}
  ```

## build_query Function

- **Parameters**:
  - `params`: A dictionary where keys are query parameters and values are their corresponding values.

- **Return Type**: A string representing the query string built from the provided dictionary.

- **Usage Examples**:
  ```python
  from url_utils import build_query

  params = {'name': 'John', 'age': 30, 'city': 'New York'}
  query = build_query(params)
  print(query)  # Output: 'name=John&age=30&city=New York'
  ```