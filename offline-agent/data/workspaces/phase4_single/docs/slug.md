# Slug Utility Documentation

## slugify Function

Converts a string to a URL-friendly slug.

**Parameters**:
- `text`: The string to convert.
- `separator`: The separator to use between words (default is "-").

**Returns**:
- A slugified string.

**Examples**:
```python
from slug_utils import slugify
slugify('Hello, World! 123')
# Output: 'hello-world-123'
```

## unslugify Function

Reverses the slugify function, converting a slug back to a string.

**Parameters**:
- `slug`: The slug to convert.
- `separator`: The separator used in the slug (default is "-").

**Returns**:
- A string.

**Examples**:
```python
from slug_utils import unslugify
unslugify('hello-world-123')
# Output: 'Hello World 123'
```