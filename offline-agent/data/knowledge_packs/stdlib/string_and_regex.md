# Python String Manipulation and Regular Expressions Guide

## Safe String Processing
When transforming text into slugs, tokens, or identifiers:
- Prefer standard string methods (`str.split()`, `str.join()`, `str.replace()`, `str.strip()`) over complex regular expressions.
- Avoid character classes with dashes like `[^ - ]` because in regex, a hyphen between spaces defines an ASCII range (`space` to `space`), leading to accidental character stripping.
- To normalize whitespace and separators:
  ```python
  cleaned = ''.join(c.lower() if c.isalnum() or c in ' _-' else '' for c in text)
  words = [w for w in cleaned.replace('_', ' ').replace('-', ' ').split() if w]
  result = separator.join(words)
  ```

## Unslugification and Capitalization
- Split on the separator, filter out empty tokens, and capitalize each word:
  ```python
  words = [w.capitalize() for w in slug.split(separator) if w]
  return ' '.join(words)
  ```

## Safe Query String Parsing
- When parsing URL query strings like `a=1&b=2`:
  - Always handle empty strings upfront (`if not query_str: return {}`).
  - Strip any leading `?` (`query_str = query_str.lstrip('?')`).
  - Only split pairs that contain `=` (`if '=' in part: k, v = part.split('=', 1)`).
  ```python
  def parse_query(query_str: str) -> dict:
      query_str = query_str.lstrip('?')
      if not query_str:
          return {}
      params = {}
      for part in query_str.split('&'):
          if '=' in part:
              k, v = part.split('=', 1)
              params[k] = v
      return params

  def build_query(params: dict) -> str:
      pairs = sorted(f"{k}={v}" for k, v in params.items())
      return "&".join(pairs)
  ```
