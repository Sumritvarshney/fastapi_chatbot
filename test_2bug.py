import os
import json

# INTENTIONAL BUG 1: Hardcoded API Key (Security Risk)
SECRET_KEY = "sk-12345-abcdef-67890"

def calc(x, y):
    # INTENTIONAL BUG 2: Bad Naming & No Type Hints
    # INTENTIONAL BUG 3: No handling for Division by Zero
    return x / y

def main():
    print("Starting process...")
    
    val1 = 10
    val2 = 0  # This will crash the code
    
    result = calc(val1, val2)
    
    # INTENTIONAL BUG 4: Using 'print' instead of proper logging
    print(f"Result is: {result}")

if __name__ == "__main__":
    main()