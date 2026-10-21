from fizz import fizzbuzz


def test_fizzbuzz_15():
    assert fizzbuzz(15)[-1] == "FizzBuzz"


def test_fizzbuzz_5():
    assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]
