import logging

def remap_x(data, width):
    min_x = min(data)
    max_x = max(data)
    if min_x == max_x:
        raise ValueError("All x values are identical")
    result = {}
    for x in sorted(data.keys()):
        y = data[x]
        # Map x in [min_x, max_x] to a bucket index in [0, width-1]
        bucket = int((x - min_x) / (max_x - min_x) * width)
        if bucket == width:  # Handle x == max_x edge case
            bucket = width - 1
        mapped_x = bucket
        result[mapped_x] = max(result.get(mapped_x, float('-inf')), y)
    return result