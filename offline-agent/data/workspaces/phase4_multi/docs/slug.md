# Slug Utils Documentation

## Slugify Function

- **Parameters**:
  - `text`: The string to be slugified.
  - `separator`: The separator to use between words. Default is `-`.

- **Return Type**: `str`

- **Usage Example**:
  ```python
  from slug_utils import slugify

  slug = slugify('Hello, World!')
  print(slug)  # Output: hello-world
  ```

## Unslugify Function

- **Parameters**:
  - `slug`: The slug string to be unslugged.
  - `separator`: The separator used in the slug. Default is `-`.

- **Return Type**: `str`

- **Usage Example**:
  ```python
  from slug_utils import unslugify

  original_text = unslugify('hello-world')
  print(original_text)  # Output: Hello, World!
  ```