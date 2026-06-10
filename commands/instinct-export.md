---
description: Export learned instincts to a JSON file for sharing.
argument-hint: <file>
---

Continuous learning crosses people, not just sessions:

```bash
python3 scripts/instincts.py export "$ARGUMENTS"
```

Report the count and destination path. Remind the recipient to import with
`/instinct-import <file>` — imported instincts arrive tagged with their origin.
