## Repair request

Some of your entities failed automated checks, or the checks found statements nothing covers. Fix each issue only from the sources:
- To revise an entity, return it in full with the same `id` (and its `key`). Fix quotes so they are exact copies of one source line, fix derivations so `from` is inside the quote and `to` equals the value, and fix values the sources do not support.
- To cover a missed statement, return a new item with no `id`.
- If the sources don't support any fix, list the issue id in `unresolved`. Never change a value just to make a check pass.
- Do not return entities that have no issue.
