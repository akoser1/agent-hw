from greeter import Greeter


def test_greet():
    assert Greeter().greet("Ada") == "Hello, Ada!"
