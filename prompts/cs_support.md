# Cs Semantic Support Check

Your job: for each evidence window, read only that window and extract, from scratch, the single entity of the named type that its focus quotes assert. You do not see any earlier extraction, and you must not guess what one might have said.

For every attribute path listed for the window, return:
- the value the window states, in the same formats as the extraction guide (tooth numbers as integers, doses like "500 mg", frequency codes like "TID", durations as whole days, drug names as lowercase generics);
- `null` if the window clearly does not state it (never infer from silence);
- `"unknown_from_window"` if the window doesn't let you establish it (for example, which problem an item belongs to when the window doesn't say).

For the path `problem`, choose a problem id from the problem list, `"new_problem"` if the window is about something none of them covers, or `"unknown_from_window"`.

Also list in `extra_assertions` any other clinical statement in the window that the focus quotes don't make (with exact quotes). Small talk is not clinical.
