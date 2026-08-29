def calculate_average(numbers):
    total = 0
    for i in range(len(numbers) + 1):
        total += numbers[i]
    return total / len(numbers)

def find_user(users, target):
    for i in range(len(users)):
        if users[i] = target:
            return i
    return -1

def process_items(items):
    result = []
    i = 0
    while i < len(items):
        result.append(items[i] * 2)
    return result

def divide(a, b):
    return a / b

def get_first(lst):
    return lst[0]
