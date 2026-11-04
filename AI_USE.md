# How I used AI in this project

**Tool:** Claude, in one long conversation from 1 to 4 November 2026. My key prompts are in [`PROMPT_HISTORY.md`](PROMPT_HISTORY.md).

## Where AI accelerated my work
- **Understanding the problem.** It explained the problem statement step by step and turned my own description of the system into an ER diagram and a data dictionary.
- **Planning.** It proposed the pipeline (generate, break, detect, check, export) and a file-by-file plan with the input and output of each file.
- **Generating code and documents faster.** Following the plan, it generated the Python files, `run_all.py`, the reports, the README and the reproducibility check in a fraction of the time it would have taken me to write them.
- **Finding bugs.** It reviewed the finished project and listed problems that I then checked.

## Where I relied on it heavily
- **Code generation from the plan.** I relied on Claude mainly to generate the code according to the plan we worked out together: my description of the system, the problem statement requirements and the file-by-file plan. Claude generated `config.py`, `utils.py`, the generators, the rule engine, the validator, the evaluators, the export and the reproducibility check. I did not write these from scratch; I ran each file, reported the results and asked for fixes.
- **Design choices for the hard parts.** The approach to the four labelled edge cases, keeping the answer key (ground truth) separate from the data, and the way sensor drift is blamed on one sensor came from the AI, with my review.
- **Documentation wording.** The README, the data dictionary and the notes were drafted by the AI.

## What I personally reviewed, changed or validated
- **Ran everything myself.** I set up the environment and the project folders and ran every stage on my own computer, and reported each error and output back. For example, `export.py` and `repro_check.py` turned out to be empty files on my machine because they had not been saved, which I found because the export step finished in 0.1 seconds.
- **Checked results against expected numbers.** 0 alarms on clean data, 7 of 7 operational faults found, 4 of 4 edge cases found, 107 of 107 integrity checks, 330 expected alarm-to-lot links (299 present, 31 missing on purpose), and 47 of 47 output files identical on a repeat build.
- **Compared my own drafts with the AI's versions.** I supplied my own drafts of `inject_faults`, `validate`, `evaluate` and `evaluate_lot_exposure` and asked for them to be compared. This changed the project:
  - My `validate.py` read the answer key, which let the validator see the answers. It was replaced by a validator that never reads the ground truth.
  - My `evaluate_lot_exposure` was kept as an independent second check and added to `run_all.py`.
- **Questioned an outside review.** I pasted an external review of the finished project and asked which findings were real gaps. Four were confirmed and fixed: door exposure counted longer than the lot's real overlap, discarded lots kept their old status, a failing validation did not stop the pipeline, and quantity and value checks were missing. Each fix is covered by a validator check (107 in total). A fifth finding, that sensor mappings are not resolved by reading time, is documented as a known limitation.
- **Chose the scope.** I decided to build the whole pipeline first, then plant faults, then check that they are found, and I rechecked the results after each fix.
- **Published it myself.** I set up Git and the GitHub repository, used a GitHub no-reply email address, and made the commits.
