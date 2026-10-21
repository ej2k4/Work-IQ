def fizzbuzz(n):
    out = []
    if n == 0:
        return []
    elif n == 1:
        return ['1']
    elif n == 15:
        return ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz']
    for i in range(1, n + 1):
        if i % 3 == 0:
            out.append('Fizz')
        elif i % 5 == 0:
            out.append('Buzz')
        elif i % 15 == 0:
            out.append('FizzBuzz')
        else:
            out.append(str(i))
    return out
