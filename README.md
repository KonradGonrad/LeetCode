<div align="center">

<h1>LeetCode Notebook</h1>

<p><strong>Solve. Experiment. Understand.</strong></p>
<p>Solutions and personal Jupyter notebooks, together in one place.</p>

<p>
  <a href="#solutions">Latest solutions</a> ·
  <a href="./solutions">All problems</a> ·
  <a href="#notebooks">Notebooks</a> ·
  <a href="#automation">Automation</a>
</p>

<img src="https://leetcard.jacoblin.cool/KonradGonradLeetCode?theme=dark" alt="KonradGonradLeetCode's LeetCode statistics" />

</div>

---

## Solutions

Expand the table to see the **10 most recently solved problems**.
Browse the [solutions directory](./solutions) for the full collection.

Results and ordering come from the original solution commits. Notebook edits
do not change a problem's position. Difficulty is read from each problem's
local README; unavailable results or difficulty are shown as **—**.

<!-- START_TABLE -->

<details>
<summary><strong>Latest 10 solved problems</strong></summary>

| Problem | Code | Notes | Time | Difficulty |
| --- | --- | --- | --- | --- |
| [995-test-problem](./solutions/995-test-problem) | [solution.py](./solutions/995-test-problem/solution.py) | [Notebook](./solutions/995-test-problem/notes.ipynb) | — | — |
| [999-test-problem](./solutions/999-test-problem) | [solution.py](./solutions/999-test-problem/solution.py) | [Notebook](./solutions/999-test-problem/notes.ipynb) | — | — |
| [14-longest-common-prefix](./solutions/14-longest-common-prefix) | [longest-common-prefix.py](./solutions/14-longest-common-prefix/longest-common-prefix.py) | [Notebook](./solutions/14-longest-common-prefix/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 19.3 MB (32.95%) | Easy |
| [2058-concatenation-of-array](./solutions/2058-concatenation-of-array) | [concatenation-of-array.py](./solutions/2058-concatenation-of-array/concatenation-of-array.py) | [Notebook](./solutions/2058-concatenation-of-array/notes.ipynb) | Time: 3 ms (18.61%) \| Memory: 19.3 MB (79.13%) | Easy |
| [50-powx-n](./solutions/50-powx-n) | [powx-n.py](./solutions/50-powx-n/powx-n.py) | [Notebook](./solutions/50-powx-n/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 19.4 MB (87.37%) | Medium |
| [13-roman-to-integer](./solutions/13-roman-to-integer) | [roman-to-integer.py](./solutions/13-roman-to-integer/roman-to-integer.py) | [Notebook](./solutions/13-roman-to-integer/notes.ipynb) | Time: 11 ms (14.09%) \| Memory: 19.3 MB (59.82%) | Easy |
| [66-plus-one](./solutions/66-plus-one) | [plus-one.py](./solutions/66-plus-one/plus-one.py) | [Notebook](./solutions/66-plus-one/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 19.4 MB (19.94%) | Easy |
| [202-happy-number](./solutions/202-happy-number) | [happy-number.py](./solutions/202-happy-number/happy-number.py) | [Notebook](./solutions/202-happy-number/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 19.4 MB (25.48%) | Easy |
| [48-rotate-image](./solutions/48-rotate-image) | [rotate-image.py](./solutions/48-rotate-image/rotate-image.py) | [Notebook](./solutions/48-rotate-image/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 19.2 MB (69.63%) | Medium |
| [898-transpose-matrix](./solutions/898-transpose-matrix) | [transpose-matrix.py](./solutions/898-transpose-matrix/transpose-matrix.py) | [Notebook](./solutions/898-transpose-matrix/notes.ipynb) | Time: 0 ms (100.00%) \| Memory: 20 MB (15.58%) | Easy |

</details>

<!-- END_TABLE -->

## Notebooks

Every problem lives in `solutions/<id>-<slug>/` with its code, problem statement,
and a **notes.ipynb** notebook.

Use the notebook to write your own implementations, explain your reasoning,
compare approaches, and try examples. Each new notebook contains a Markdown
cell and an empty Python code cell. GitHub can preview it directly through the
**Notes** link above.

To edit and run notebooks locally, open them in VS Code with Jupyter support,
or use JupyterLab:

```bash
python3 -m pip install jupyterlab
jupyter lab
```

Existing notebooks are never overwritten. When migrating an older `notes.md`,
its text is copied into the notebook before the Markdown file is removed.
If both files already exist, both are preserved.

## Automation

The organizer uses only the **Python standard library**. It makes no API
requests and does not categorize problems.

```bash
python3 scripts/organizer.py
```

The workflow currently runs on the **test** branch for solution changes, and
can also be started manually from GitHub Actions.

1. Keep each problem directly in `solutions/`; migrate folders from the former
   `Algorithm/`, `Database/`, and `Pandas/` locations when needed.
2. Create missing notebooks and preserve the original solution commit in
   `.leetsync.json`.
3. Commit each changed problem using its original LeetSync message.
4. Refresh the latest ten entries and create a separate `Update README` commit.

Configure Git's `user.name` and `user.email` before running locally.
Incoming solutions must already be committed. The script creates local commits;
GitHub Actions pushes them after a successful run.

Repeated runs with unchanged files create no new commits. Conflicting folders
are preserved for manual resolution, and unrelated staged files are excluded.
The section between the HTML table markers is maintained automatically.
