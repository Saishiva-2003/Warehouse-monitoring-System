# Prompt history: key development prompts

This file lists the prompts that shaped the main features of the project. The text of each prompt is copied exactly as I sent it, including spelling mistakes, except where a prompt is marked "summarised, not quoted". Pasted terminal output and long attachments are summarised in one line. Each prompt has a short summary of its purpose and result. Times are in Indian Standard Time (IST, UTC+05:30), taken from the conversation record.

AI tool: Claude, one continuous conversation from 1 to 3 November 2026. The AI wrote most of the code. I set up the environment, ran every stage on my own machine, reported results back, and compared my own drafts of the injection, validation and evaluation scripts with the AI's versions.


## Phase 1: Understanding the problem

### Prompt 1  -  01 Nov 2026, 21:25 IST

**Purpose:** Shared the full problem statement and asked for a clear explanation of the project.

**Prompt:** (pasted terminal output, summarised)

**Result:** Scope, entities, ID formats, scale and the four labelled edge cases.

### Prompt 2  -  01 Nov 2026, 21:55 IST

**Purpose:** Described my understanding of the system for the AI to confirm.

**Prompt (exact text):**

> see i will explain this clearly in an technical way see the thing is there an warehouse management where there are  multiple zones and for every zone there will an sensor, where the zones have the product lot like different product with same condition will be stored in the zones where for each product lot there will be some rules then the system need to identify if any rule is breaked according to the sensor reading , and also which rule is broken and also which product are effected then it need to get alaram and after that there will be inspection and then there will be remediation this are the things right is this right or not

**Result:** Confirmed domain model: warehouse, zones, sensors, lots with storage rules, alarms, inspections, remediations.

### Prompt 3  -  01 Nov 2026, 21:58 IST

**Purpose:** Requested the data model documentation.

**Prompt (exact text):**

> ER diagram and data dictionary

**Result:** ER diagram and data dictionary for the 10 entities plus bridge and history tables.

### Prompt 4  -  02 Nov 2026, 06:30 IST

**Purpose:** Asked for the development process and whether a database is needed.

**Prompt (summarised, not quoted):**

> Asked for a step-by-step explanation of how the application should be developed and why, whether a database is needed and how to implement the business logic, and for the complete setup details.

**Result:** Design decision: scripts exchange CSV files; SQL is produced only as an export.

### Prompt 5  -  02 Nov 2026, 06:42 IST

**Purpose:** Asked for a file-by-file development plan with inputs and outputs per file.

**Prompt (exact text):**

> See explain me the complete project making process what what need to develop file wise what we need to develop in the each file and also i have lot of confusion in the input and Output give me a proper and proper walk through to the complete project so tthat we can develop the project easily

**Result:** File-level plan: config, helpers, generators, rule engine, fault injection, validation, evaluation.

## Phase 2: Building the generator

### Prompt 6  -  02 Nov 2026, 15:14 IST

**Purpose:** Requested the central configuration module.

**Prompt (exact text):**

> give me the code for the config.py

**Result:** config.py: fixed seed 20261022 and two scales (starter, full) sharing one generator.

## Phase 3: Fault injection, validation and evaluation

### Prompt 7  -  03 Nov 2026, 08:17 IST

**Purpose:** Submitted my own draft of the fault-injection script for review.

**Prompt (exact typed text; the file itself is omitted):**

> this is inject-faults.py

**Result:** Revised version: varied seeded fault times, no labels leaking into the data, ground truth stored separately.

### Prompt 8  -  03 Nov 2026, 08:25 IST

**Purpose:** Asked for the expected results of the pipeline and the reasoning.

**Prompt (exact text):**

> see first say mw what will the expected output for our project and why

**Result:** Agreed reference numbers per stage: 0 alarms on clean data, 7 operational alarms, 4 edge-case findings.

### Prompt 9  -  03 Nov 2026, 08:39 IST

**Purpose:** Submitted my own validator draft for comparison.

**Prompt (exact typed text; the file itself is omitted):**

> verify the code with the code which you have given above

**Result:** Replacement validator that never reads the ground truth (all four edge cases detected).

### Prompt 10  -  03 Nov 2026, 08:51 IST

**Purpose:** Submitted my own evaluation script for comparison with the AI's design.

**Prompt (exact typed text; the file itself is omitted):**

> compare this with the expected on which you have given and give me the code according to that

**Result:** One merged evaluator with one-to-one matching, precision, recall, F1 and alarm-lot linkage.

### Prompt 11  -  03 Nov 2026, 09:13 IST

**Purpose:** Asked which files in the pipeline folder were unnecessary or missing.

**Prompt (exact text):**

> in my pipeline path there are files like Evaluate lot exposer, generate lots , generate readings, generate master , evaluate,export,inject defects , inject faults, repro check, rule enigne , test data integration , timeline, validation this files are there now say me is ther any py file which are not require say the file name i will remove then or if any functinalitu is missing we will add them if you require the code of that file i will give to you to understand

**Result:** Review of every file; confirmed which are part of the main run.

### Prompt 12  -  03 Nov 2026, 09:14 IST

**Purpose:** Submitted my own lot-exposure evaluation script.

**Prompt:** I attached my script with no extra text.

**Result:** Kept as an independent second check of all alarm-lot verdicts; added to run_all.py.

## Phase 4: Review findings and verification

### Prompt 13  -  03 Nov 2026, 09:24 IST

**Purpose:** Ran the reproducibility check on my own machine and reported the result.

**Prompt:** (pasted terminal output, summarised)

**Result:** Two complete builds produced 47 of 47 identical files.

### Prompt 14  -  03 Nov 2026, 19:15 IST

**Purpose:** Pasted an external review of the project and asked whether each finding was a real gap.

**Prompt (exact text; the pasted review that came with it is omitted):**

> check this this are the question i got is this really the gaps if yes ask why , if not where it is covered'

**Result:** Four real defects confirmed and fixed (exposure overlap, discarded lot status, validator exit code, missing value checks); one documented limitation; 107 validation checks.