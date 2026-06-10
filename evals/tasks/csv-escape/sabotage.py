def to_csv_row(fields):  # quotes when needed but forgets to double inner quotes
    out = []
    for f in fields:
        if any(c in f for c in ',"\r\n'):
            out.append('"' + f + '"')
        else:
            out.append(f)
    return ",".join(out)
