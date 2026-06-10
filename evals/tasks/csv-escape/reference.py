def to_csv_row(fields):
    out = []
    for f in fields:
        if any(c in f for c in ',"\r\n'):
            out.append('"' + f.replace('"', '""') + '"')
        else:
            out.append(f)
    return ",".join(out)
