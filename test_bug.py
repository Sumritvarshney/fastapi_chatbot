# test_bug.py

def calculate(x,y):
    # This function has bad naming and no type hints
    # It also doesn't handle division by zero
    return x / y

print(calculate(10, 0))